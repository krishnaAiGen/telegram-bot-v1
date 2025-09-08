
# backend/main.py

# --- 1. Standard & Library Imports ---
import os
import requests
import time
from typing import Dict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cryptography.fernet import Fernet
from typing import Optional

# --- 2. Firebase & Platform Imports ---
import firebase_admin
from firebase_admin import credentials, auth, firestore
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

# --- 3. Local Project Imports ---
from persona_management.pipeline import run_persona_factory_pipeline

# --- 4. Initialization ---
load_dotenv()
cred_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'firebase-credentials.json')
if not os.path.exists(cred_path):
    raise FileNotFoundError(f"Firebase credentials not found at {cred_path}")
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()
app = FastAPI(title="AI Persona Bot Backend API")

# --- 5. CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 6. Encryption Setup ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set in .env file for encryption.")
fernet = Fernet(SECRET_KEY.encode())

# --- 7. In-Memory Connection Manager ---
class TelegramConnectionManager:
    def __init__(self):
        self.pending_connections: Dict[str, TelegramClient] = {}
    def add_client(self, user_id: str, client: TelegramClient): self.pending_connections[user_id] = client
    def get_client(self, user_id: str) -> TelegramClient | None: return self.pending_connections.get(user_id)
    def remove_client(self, user_id: str):
        if user_id in self.pending_connections: del self.pending_connections[user_id]
connection_manager = TelegramConnectionManager()

# --- 8. Pydantic Models (Single Source of Truth) ---
class UserCredentials(BaseModel):
    email: EmailStr
    password: str
class AuthResponse(BaseModel):
    idToken: str
    email: EmailStr
class ConnectionKeyRequest(BaseModel):
    api_key: str
class ConnectionStatusResponse(BaseModel):
    has_openai_key: bool
class GenerationRequest(BaseModel):
    goal: str
class DraftUpdateRequest(BaseModel):
    activeTeam: list
class StartBotRequest(BaseModel):
    platforms: list[str]
class TelegramStartRequest(BaseModel):
    api_id: str
    api_hash: str
    phone_number: str
class TelegramCodeRequest(BaseModel):
    code: str
class TelegramPasswordRequest(BaseModel):
    password: str
class SlackConnectionRequest(BaseModel):
    bot_token: str
    app_token: str
    channel_id: str
class DiscordConnectionRequest(BaseModel):
    bot_token: str
    channel_id: str
class BotConfigRequest(BaseModel):
    triage_model: str
    random_response_rate: float
    min_initiate_hours: int
    response_context_messages: int
class ServiceKeysRequest(BaseModel):
    openai: Optional[dict] = None
    grok: Optional[dict] = None
    mem0: Optional[dict] = None

# --- 9. Security & Helper Functions (Defined Before Use) ---
security = HTTPBearer()
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        id_token = credentials.credentials
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token['uid']
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")

def is_telegram_connection_valid(data: dict) -> bool:
    if not data: return False
    ingestor = data.get("ingestor_config", {})
    senders = data.get("senders_config", {})
    return all([
        "session_string_encrypted" in ingestor,
        bool(senders) and all("session_string_encrypted" in s for s in senders.values()),
        "telegram_group_id" in data and data["telegram_group_id"]
    ])
def is_slack_connection_valid(data: dict) -> bool:
    if not data: return False
    return all(k in data for k in ["bot_token_encrypted", "app_token_encrypted", "channel_id"])
def is_discord_connection_valid(data: dict) -> bool:
    if not data: return False
    return all(k in data for k in ["bot_token_encrypted", "channel_id"])

async def _finalize_telegram_connection(client: TelegramClient) -> dict:
    session_string = client.session.save()
    encrypted_session = fernet.encrypt(session_string.encode()).decode()
    return {"status": "success", "session_string_encrypted": encrypted_session, "api_id": client.api_id, "api_hash": client.api_hash}


# --- Authentication ---
@app.post("/auth/register", status_code=201, tags=["Authentication"])
async def register(credentials: UserCredentials):
    # ... (This function remains the same)
    try:
        user = auth.create_user(email=credentials.email, password=credentials.password)
        user_doc_ref = db.collection("customers").document(user.uid)
        user_doc_ref.set({"email": user.email, "createdAt": firestore.SERVER_TIMESTAMP, "personaConfig": {"draftTeam": [], "liveTeam": []}})
        return {"message": "User created successfully.", "uid": user.uid}
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=409, detail=f"User with email {credentials.email} already exists.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
async def login(credentials: UserCredentials):
    # ... (This function remains the same)
    firebase_api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not firebase_api_key: raise HTTPException(status_code=500, detail="Firebase Web API Key not configured.")
    rest_api_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
    payload = {"email": credentials.email, "password": credentials.password, "returnSecureToken": True}
    try:
        response = requests.post(rest_api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        return AuthResponse(idToken=data['idToken'], email=data['email'])
    except requests.exceptions.HTTPError as err:
        error_detail = err.response.json().get("error", {}).get("message", "Invalid credentials.")
        raise HTTPException(status_code=401, detail=error_detail)

# --- Persona Management ---
@app.get("/api/config", tags=["Persona Management"])
async def get_user_config(uid: str = Depends(get_current_user)):
    try:
        db = firestore.client()
        doc = db.collection("customers").document(uid).get()
        if doc.exists:
            return doc.to_dict().get("personaConfig", {})
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/personas/generate", tags=["Persona Management"])
async def generate_personas(request: GenerationRequest, uid: str = Depends(get_current_user)):
    db = firestore.client()
    try:
        doc = db.collection("customers").document(uid).collection("connections").document("openai").get()
        if not doc.exists: raise HTTPException(status_code=400, detail="OpenAI API key not found.")
        encrypted_key = doc.to_dict().get("encrypted_key")
        decrypted_key = fernet.decrypt(encrypted_key.encode()).decode()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not retrieve or decrypt API key: {str(e)}")
    try:
        pipeline_result = await run_persona_factory_pipeline(initial_prompt=request.goal, api_key=decrypted_key)
        if pipeline_result.get("status") != "success": raise RuntimeError(pipeline_result.get("reason", "Unknown failure"))
        generated_personas = pipeline_result.get("personas", [])
        if not generated_personas: raise HTTPException(status_code=500, detail="Generation produced no personas.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during persona generation: {str(e)}")
    try:
        user_doc_ref = db.collection("customers").document(uid)
        current_timestamp = int(time.time())
        for i, persona in enumerate(generated_personas):
            persona['id'] = f"draft_{current_timestamp}_{i}"
        user_doc_ref.set({"personaConfig": {"draftTeam": generated_personas, "lastUpdated": firestore.SERVER_TIMESTAMP}}, merge=True)
        return {"message": "Personas generated and saved to your draft successfully!", "personas": generated_personas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save generated personas: {str(e)}")

@app.put("/api/draft", status_code=200, tags=["Persona Management"])
async def update_draft_team(request: DraftUpdateRequest, uid: str = Depends(get_current_user)):
    try:
        db = firestore.client()
        user_doc_ref = db.collection("customers").document(uid)
        user_doc_ref.set({"personaConfig": {"draftTeam": request.activeTeam, "lastUpdated": firestore.SERVER_TIMESTAMP}}, merge=True)
        return {"message": "Draft saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save draft: {str(e)}")

@app.post("/api/deploy", status_code=200, tags=["Persona Management"])
async def deploy_team(uid: str = Depends(get_current_user)):
    try:
        db = firestore.client()
        doc = db.collection("customers").document(uid).get()
        if not doc.exists: raise HTTPException(status_code=404, detail="User data not found.")
        draft_team = doc.to_dict().get("personaConfig", {}).get("draftTeam", [])
        if not draft_team: raise HTTPException(status_code=400, detail="Cannot deploy an empty team.")
        user_doc_ref = db.collection("customers").document(uid)
        user_doc_ref.set({"personaConfig": {"liveTeam": draft_team, "lastDeployed": firestore.SERVER_TIMESTAMP}}, merge=True)
        return {"message": "Team deployed successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

# --- Bot Configuration (NEW) ---
@app.get("/api/connections/all", tags=["Bot Configuration"])
async def get_all_connections(uid: str = Depends(get_current_user)):
    try:
        connections = {}
        connections_ref = db.collection("customers").document(uid).collection("connections")
        for doc in connections_ref.stream():
            connections[doc.id] = doc.to_dict()
        return connections
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/config/behavior", status_code=200, tags=["Bot Configuration"])
async def save_bot_configuration(request: BotConfigRequest, uid: str = Depends(get_current_user)):
    try:
        user_doc_ref = db.collection("customers").document(uid)
        user_doc_ref.set({"personaConfig": request.dict()}, merge=True)
        return {"message": "Behavior settings saved."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/connections/keys", status_code=200, tags=["Bot Configuration"])
async def save_service_keys(request: ServiceKeysRequest, uid: str = Depends(get_current_user)):
    try:
        connections_ref = db.collection("customers").document(uid).collection("connections")
        for service, data in request.dict().items():
            if data is None:
                continue 
            key_to_encrypt = data.get("key") or data.get("api_key")
            encrypted_key = fernet.encrypt(key_to_encrypt.encode()).decode()
            connections_ref.document(service).set({"api_key_encrypted": encrypted_key}, merge=True)
        return {"message": "API keys saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Bot Control ---
@app.post("/api/start", status_code=200, tags=["Bot Control"])
async def start_bot(request: StartBotRequest, uid: str = Depends(get_current_user)):
    db = firestore.client()
    doc = db.collection("customers").document(uid).get()
    if not doc.exists: raise HTTPException(status_code=404, detail="User data not found.")
    if not doc.to_dict().get("personaConfig", {}).get("liveTeam", []): raise HTTPException(status_code=400, detail="You must deploy a team before starting.")
    if not request.platforms: raise HTTPException(status_code=400, detail="You must select at least one platform to start.")
    connections_ref = db.collection("customers").document(uid).collection("connections")
    for platform in request.platforms:
        connection_doc = connections_ref.document(platform).get()
        if not connection_doc.exists: raise HTTPException(status_code=428, detail=f"Connection required for {platform}.")
        is_valid = False
        platform_data = connection_doc.to_dict()

        if platform == "telegram":
            is_valid = is_telegram_connection_valid(platform_data)
        elif platform == "slack":
            is_valid = is_slack_connection_valid(platform_data)
        elif platform == "discord":
            is_valid = is_discord_connection_valid(platform_data)        
        if not is_valid: raise HTTPException(status_code=428, detail=f"Configuration for {platform} is incomplete.")
    user_doc_ref = db.collection("customers").document(uid)
    user_doc_ref.set({"personaConfig": {"isActive": True, "activePlatforms": request.platforms, "lastStarted": firestore.SERVER_TIMESTAMP}}, merge=True)
    return {"message": f"Bot start signal sent for: {', '.join(request.platforms)}."}

@app.post("/api/stop", status_code=200, tags=["Bot Control"])
async def stop_bot(uid: str = Depends(get_current_user)):
    try:
        db = firestore.client()
        user_doc_ref = db.collection("customers").document(uid)
        user_doc_ref.set({"personaConfig": {"isActive": False, "lastStopped": firestore.SERVER_TIMESTAMP}}, merge=True)
        return {"message": "Bot stop signal sent successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

# --- Platform Connections ---
@app.post("/api/connections/openai", status_code=201, tags=["Platform Connections"])
async def save_openai_key(request: ConnectionKeyRequest, uid: str = Depends(get_current_user)):
    db = firestore.client()
    encrypted_key = fernet.encrypt(request.api_key.encode()).decode()
    connections_ref = db.collection("customers").document(uid).collection("connections").document("openai")
    connections_ref.set({"encrypted_key": encrypted_key, "lastUpdated": firestore.SERVER_TIMESTAMP})
    return {"message": "OpenAI key saved successfully."}


@app.get("/api/connections/status", response_model=ConnectionStatusResponse, tags=["Platform Connections"])
async def get_connection_status(uid: str = Depends(get_current_user)):
    db = firestore.client()
    doc = db.collection("customers").document(uid).collection("connections").document("openai").get()
    return ConnectionStatusResponse(has_openai_key=doc.exists)

@app.get("/api/connections", tags=["Platform Connections"])
async def get_all_connections_status(uid: str = Depends(get_current_user)):
    db = firestore.client()
    doc = db.collection("customers").document(uid).get()
    if not doc.exists: return []
    
    persona_config = doc.to_dict().get("personaConfig", {})
    active_platforms = persona_config.get("activePlatforms", [])
    connections_ref = db.collection("customers").document(uid).collection("connections")
    supported_platforms = ["telegram", "discord", "slack"]
    status_list = []
    
    for platform in supported_platforms:
        doc = connections_ref.document(platform).get()
        is_connected = False
        if doc.exists:
            platform_data = doc.to_dict()
            # --- THIS IS THE FIX ---
            if platform == "telegram":
                is_connected = is_telegram_connection_valid(platform_data)
            elif platform == "slack":
                is_connected = is_slack_connection_valid(platform_data)
            elif platform == "discord":
                is_connected = is_discord_connection_valid(platform_data)
            # ------------------------
        
        status_list.append({
            "platform": platform, 
            "isConnected": is_connected, 
            "isActiveNow": platform in active_platforms
        })
    return status_list

@app.get("/api/connections/telegram", tags=["Platform Connections"])
async def get_telegram_settings(uid: str = Depends(get_current_user)):
    """Fetches the user's complete Telegram configuration document."""
    try:
        db = firestore.client()
        doc = db.collection("customers").document(uid).collection("connections").document("telegram").get()
        if doc.exists:
            return doc.to_dict()
        return {} # Return an empty object if no settings exist yet
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/connections/telegram", tags=["Platform Connections"])
async def save_telegram_settings(request: dict, uid: str = Depends(get_current_user)):
    """Saves/Overwrites the entire Telegram operational settings object."""
    try:
        db = firestore.client()
        doc_ref = db.collection("customers").document(uid).collection("connections").document("telegram")
        # Overwrite the document with the new settings from the frontend.
        doc_ref.set(request) # merge=False is the default for .set()
        return {"message": "Telegram settings saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")

@app.post("/api/connections/telegram/start_auth", tags=["Platform Connections"])
async def telegram_connection_start(request: TelegramStartRequest, uid: str = Depends(get_current_user)):
    """STEP 1: Initiates the Telegram connection and requests the OTP code."""
    try:
        client = TelegramClient(StringSession(), int(request.api_id), request.api_hash)
        await client.connect()
        await client.send_code_request(request.phone_number)
        connection_manager.add_client(uid, client)
        return {"status": "code_needed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Telegram connection failed: {str(e)}")

@app.post("/api/connections/telegram/submit_code", tags=["Platform Connections"])
async def telegram_connection_submit_code(request: TelegramCodeRequest, uid: str = Depends(get_current_user)):
    """STEP 2: Submits the OTP code."""
    client = connection_manager.get_client(uid)
    if not client: raise HTTPException(status_code=408, detail="Connection timed out. Please start over.")
    try:
        await client.sign_in(code=request.code)
        connection_manager.remove_client(uid)
        return await _finalize_telegram_connection(client)
    except SessionPasswordNeededError:
        return {"status": "password_needed"}
    except Exception as e:
        if client.is_connected(): await client.disconnect()
        connection_manager.remove_client(uid)
        raise HTTPException(status_code=400, detail=f"Failed to submit code: {str(e)}")

@app.post("/api/connections/telegram/submit_password", tags=["Platform Connections"])
async def telegram_connection_submit_password(request: TelegramPasswordRequest, uid: str = Depends(get_current_user)):
    """STEP 3: Submits the 2FA password."""
    client = connection_manager.get_client(uid)
    if not client: raise HTTPException(status_code=408, detail="Connection timed out. Please start over.")
    try:
        await client.sign_in(password=request.password)
        connection_manager.remove_client(uid)
        return await _finalize_telegram_connection(client)
    except Exception as e:
        if client.is_connected(): await client.disconnect()
        connection_manager.remove_client(uid)
        raise HTTPException(status_code=400, detail=f"Failed to sign in with password: {str(e)}")
    

@app.put("/api/connections/slack", status_code=200, tags=["Platform Connections"])
async def save_slack_connection(request: SlackConnectionRequest, uid: str = Depends(get_current_user)):
    """
    Validates, encrypts, and saves/overwrites a user's Slack credentials.
    """
    try:
        # Basic validation for token formats
        if not request.bot_token.startswith("xoxb-"):
            raise HTTPException(status_code=400, detail="Invalid Slack Bot Token format.")
        if not request.app_token.startswith("xapp-"):
            raise HTTPException(status_code=400, detail="Invalid Slack App Token format.")

        # Encrypt all sensitive credentials before storing
        encrypted_bot_token = fernet.encrypt(request.bot_token.encode()).decode()
        encrypted_app_token = fernet.encrypt(request.app_token.encode()).decode()

        # Save the complete configuration to the 'slack' document
        doc_ref = db.collection("customers").document(uid).collection("connections").document("slack")
        doc_ref.set({
            "bot_token_encrypted": encrypted_bot_token,
            "app_token_encrypted": encrypted_app_token,
            "channel_id": request.channel_id,
            "lastUpdated": firestore.SERVER_TIMESTAMP
        })
        
        return {"message": "Slack connected successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect Slack: {str(e)}")


@app.put("/api/connections/discord", status_code=200, tags=["Platform Connections"])
async def save_discord_connection(request: DiscordConnectionRequest, uid: str = Depends(get_current_user)):
    """
    Encrypts and saves/overwrites a user's Discord credentials.
    """
    try:
        # Encrypt the sensitive bot token
        encrypted_bot_token = fernet.encrypt(request.bot_token.encode()).decode()

        # Save the complete configuration to the 'discord' document
        doc_ref = db.collection("customers").document(uid).collection("connections").document("discord")
        doc_ref.set({
            "bot_token_encrypted": encrypted_bot_token,
            "channel_id": request.channel_id,
            "lastUpdated": firestore.SERVER_TIMESTAMP
        })
        
        return {"message": "Discord connected successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect Discord: {str(e)}")
    
def is_slack_connection_valid(connection_data: dict) -> bool:
    """Authoritative check for a complete Slack configuration."""
    if not connection_data: return False
    # A valid connection must have all three encrypted credentials/settings.
    return all(k in connection_data for k in [
        "bot_token_encrypted", 
        "app_token_encrypted", 
        "channel_id"
    ])

def is_discord_connection_valid(connection_data: dict) -> bool:
    """Authoritative check for a complete Discord configuration."""
    if not connection_data: return False
    # A valid connection must have both the encrypted token and the channel ID.
    return all(k in connection_data for k in [
        "bot_token_encrypted",
        "channel_id"
    ])