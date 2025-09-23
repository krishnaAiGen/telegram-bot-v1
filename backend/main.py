# File: backend/main.py

# --- 1. Standard & Library Imports ---
import os
import requests
import time
import logging
import asyncio
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cryptography.fernet import Fernet
from contextlib import asynccontextmanager

# --- 2. Firebase & Platform Imports ---
import firebase_admin
from firebase_admin import credentials, auth, firestore
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

# --- 3. Local Project Imports ---
# NOTE: Ensure your shell is running from the project's root `backend/` directory
# for these top-level imports to work correctly.
from persona_management.pipeline import run_persona_factory_pipeline
from src.orchestrator import start_orchestrator_task, stop_orchestrator_task
from src.config.logging_config import setup_logging
# --- 4. Initialization & Lifespan Manager ---
setup_logging()
logger = logging.getLogger(__name__)
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's startup and shutdown events.
    The orchestrator is started in the background on startup and
    gracefully stopped on shutdown.
    """
    # --- Code here runs ONCE on Uvicorn startup ---
    logger.info("API Server starting up...")
    start_orchestrator_task() # Start the bot orchestrator in the background

    yield # The API is now running and handling requests

    # --- Code here runs ONCE on Uvicorn shutdown (e.g., Ctrl+C) ---
    logger.info("API Server shutting down...")
    await stop_orchestrator_task() # Gracefully stop the bot orchestrator

# --- FastAPI App Initialization ---
cred_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'firebase-credentials.json')
if not os.path.exists(cred_path):
    logger.critical(f"Firebase credentials not found at {cred_path}")
    raise FileNotFoundError(f"Firebase credentials not found at {cred_path}")

cred = credentials.Certificate(cred_path)
# Safety check to prevent re-initialization errors during hot-reloading
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
app = FastAPI(title="AI Persona Bot Backend API (Unified)", lifespan=lifespan)

# --- 5. CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 6. Encryption Setup ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.critical("FATAL: No SECRET_KEY set for encryption.")
    raise ValueError("No SECRET_KEY set for encryption.")
fernet = Fernet(SECRET_KEY.encode())

# --- 7. In-Memory Connection Manager ---
class TelegramConnectionManager:
    def __init__(self):
        self.pending_connections: Dict[str, TelegramClient] = {}
    def add_client(self, user_id: str, client: TelegramClient): self.pending_connections[user_id] = client
    def get_client(self, user_id: str) -> Optional[TelegramClient]: return self.pending_connections.get(user_id)
    def remove_client(self, user_id: str):
        if user_id in self.pending_connections: del self.pending_connections[user_id]
connection_manager = TelegramConnectionManager()

# --- 8. Pydantic Models ---
class UserCredentials(BaseModel): email: EmailStr; password: str
class AuthResponse(BaseModel): idToken: str; email: EmailStr
class GenerationRequest(BaseModel): goal: str
class DraftUpdateRequest(BaseModel): activeTeam: list
class StartBotRequest(BaseModel): platforms: list[str]
class TelegramStartRequest(BaseModel): api_id: str; api_hash: str; phone_number: str
class TelegramCodeRequest(BaseModel): code: str
class TelegramPasswordRequest(BaseModel): password: str
class SlackConnectionRequest(BaseModel): bot_token: str; app_token: str; channel_id: str
class DiscordConnectionRequest(BaseModel): bot_token: str; channel_id: str
class BotConfigRequest(BaseModel):
    triage_model: str
    random_response_rate: float
    min_initiate_hours: int
    response_context_messages: int
class ServiceKeysRequest(BaseModel):
    openai: Optional[dict] = None
    grok: Optional[dict] = None
    mem0: Optional[dict] = None

# --- 9. Security & Helper Functions ---
security = HTTPBearer()
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        id_token = credentials.credentials
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token['uid']
    except Exception as e:
        logger.error(f"Token verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")

def is_telegram_connection_valid(data: dict) -> bool:
    if not data: return False
    ingestor = data.get("ingestor_config", {})
    senders = data.get("senders_config", {})
    return all([ "session_string_encrypted" in ingestor, bool(senders) and all("session_string_encrypted" in s for s in senders.values()), "telegram_group_id" in data and data["telegram_group_id"] ])
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

# --- 10. API Endpoints ---

@app.post("/auth/register", status_code=201, tags=["Authentication"])
async def register(credentials: UserCredentials):
    logger.info(f"Received registration request for email: {credentials.email}")
    try:
        user = auth.create_user(email=credentials.email, password=credentials.password)
        db.collection("customers").document(user.uid).set({ "email": user.email, "createdAt": firestore.SERVER_TIMESTAMP, "personaConfig": {} })
        logger.info(f"Successfully created user with UID: {user.uid}")
        return {"message": "User created successfully.", "uid": user.uid}
    except auth.EmailAlreadyExistsError:
        logger.warning(f"Registration failed: email {credentials.email} already exists.")
        raise HTTPException(status_code=409, detail=f"User with email {credentials.email} already exists.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during registration for {credentials.email}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
async def login(credentials: UserCredentials):
    logger.info(f"Received login request for email: {credentials.email}")
    firebase_api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not firebase_api_key:
        logger.critical("Firebase Web API Key not configured on server.")
        raise HTTPException(status_code=500, detail="Firebase Web API Key not configured.")
    rest_api_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
    payload = {"email": credentials.email, "password": credentials.password, "returnSecureToken": True}
    try:
        response = requests.post(rest_api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Login successful for {credentials.email}")
        return AuthResponse(idToken=data['idToken'], email=data['email'])
    except requests.exceptions.HTTPError as err:
        error_detail = err.response.json().get("error", {}).get("message", "Invalid credentials.")
        logger.warning(f"Login failed for {credentials.email}: {error_detail}")
        raise HTTPException(status_code=401, detail=error_detail)

@app.get("/api/config", tags=["Persona Management"])
async def get_user_config(uid: str = Depends(get_current_user)):
    logger.info(f"Fetching personaConfig for user: {uid}")
    doc = db.collection("customers").document(uid).get()
    return doc.to_dict().get("personaConfig", {}) if doc.exists else {}

@app.post("/api/personas/generate", tags=["Persona Management"])
async def generate_personas(request: GenerationRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Received persona generation request for user: {uid}")
    try:
        doc = db.collection("customers").document(uid).collection("connections").document("openai").get()
        if not doc.exists:
            raise HTTPException(status_code=400, detail="OpenAI API key not found.")
        encrypted_key_value = doc.to_dict().get("api_key_encrypted") or doc.to_dict().get("encrypted_key")
        if not encrypted_key_value:
            raise HTTPException(status_code=400, detail="OpenAI API key value is missing.")

        decrypted_key = fernet.decrypt(encrypted_key_value.encode()).decode()
        pipeline_result = await run_persona_factory_pipeline(initial_prompt=request.goal, api_key=decrypted_key)
        if pipeline_result.get("status") != "success":
            raise RuntimeError(pipeline_result.get("reason", "Unknown failure"))
        generated_personas = pipeline_result.get("personas", [])
        if not generated_personas:
            raise HTTPException(status_code=500, detail="Generation produced no personas.")
        current_timestamp = int(time.time())
        for i, persona in enumerate(generated_personas):
            persona['id'] = f"draft_{current_timestamp}_{i}"
        db.collection("customers").document(uid).set({"personaConfig": {"draftTeam": generated_personas}}, merge=True)
        logger.info(f"Successfully generated and saved {len(generated_personas)} personas for user {uid}.")
        return {"message": "Personas generated successfully!", "personas": generated_personas}
    except Exception as e:
        logger.error(f"Persona generation failed for user {uid}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.put("/api/draft", tags=["Persona Management"])
async def update_draft_team(request: DraftUpdateRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Updating draft team for user: {uid}")
    db.collection("customers").document(uid).set({"personaConfig": {"draftTeam": request.activeTeam}}, merge=True)
    return {"message": "Draft saved."}

@app.post("/api/deploy", tags=["Persona Management"])
async def deploy_team(uid: str = Depends(get_current_user)):
    logger.info(f"Deploying team for user: {uid}")
    doc = db.collection("customers").document(uid).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found.")
    draft_team = doc.to_dict().get("personaConfig", {}).get("draftTeam", [])
    if not draft_team:
        raise HTTPException(status_code=400, detail="Cannot deploy an empty team.")
    db.collection("customers").document(uid).set({"personaConfig": {"liveTeam": draft_team, "lastDeployed": firestore.SERVER_TIMESTAMP}}, merge=True)
    logger.info(f"Successfully deployed {len(draft_team)} personas for user {uid}.")
    return {"message": "Team deployed successfully!"}

@app.get("/api/connections/all", tags=["Bot Configuration"])
async def get_all_connections(uid: str = Depends(get_current_user)):
    logger.info(f"Fetching all connections for user: {uid}")
    try:
        connections = {}
        connections_ref = db.collection("customers").document(uid).collection("connections")
        for doc in connections_ref.stream():
            data = doc.to_dict()
            sanitized_data = {}
            for key, value in data.items():
                if "encrypted" in key:
                    sanitized_data[key] = True # Signal that a key is present but don't expose it
                else:
                    sanitized_data[key] = value
            connections[doc.id] = sanitized_data
        return connections
    except Exception as e:
        logger.error(f"Failed to fetch connections for user {uid}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch connections: {str(e)}")

@app.put("/api/config/behavior", tags=["Bot Configuration"])
async def save_bot_configuration(request: BotConfigRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Saving behavior configuration for user: {uid}")
    db.collection("customers").document(uid).set({"personaConfig": request.dict()}, merge=True)
    return {"message": "Behavior settings saved."}

@app.put("/api/connections/keys", tags=["Bot Configuration"])
async def save_service_keys(request: ServiceKeysRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Saving service API keys for user: {uid}")
    connections_ref = db.collection("customers").document(uid).collection("connections")
    for service, data in request.dict().items():
        if data and data.get("api_key"):
            encrypted_key = fernet.encrypt(data["api_key"].encode()).decode()
            connections_ref.document(service).set({"api_key_encrypted": encrypted_key}, merge=True)
            logger.info(f"Saved new key for service: {service} for user: {uid}")
    return {"message": "API keys saved."}

@app.post("/api/start", tags=["Bot Control"])
async def start_bot(request: StartBotRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Received start bot request for user: {uid} on platforms: {request.platforms}")
    doc_ref = db.collection("customers").document(uid)
    doc = doc_ref.get()
    if not doc.exists or not doc.to_dict().get("personaConfig", {}).get("liveTeam"):
        raise HTTPException(status_code=400, detail="You must deploy a team first.")
    if not request.platforms:
        raise HTTPException(status_code=400, detail="You must select at least one platform.")
    
    connections_ref = doc_ref.collection("connections")
    for platform in request.platforms:
        conn_doc = connections_ref.document(platform).get()
        if not conn_doc.exists:
            raise HTTPException(status_code=428, detail=f"Connection required for {platform}.")
        is_valid = False
        data = conn_doc.to_dict()
        if platform == "telegram": is_valid = is_telegram_connection_valid(data)
        elif platform == "slack": is_valid = is_slack_connection_valid(data)
        elif platform == "discord": is_valid = is_discord_connection_valid(data)
        if not is_valid:
            raise HTTPException(status_code=428, detail=f"Configuration for {platform} is incomplete.")
            
    doc_ref.set({"personaConfig": {"isActive": True, "activePlatforms": request.platforms}}, merge=True)
    logger.info(f"Set isActive=true for user {uid}. Orchestrator will now take over.")
    return {"message": f"Bot start signal sent for: {', '.join(request.platforms)}."}

@app.post("/api/stop", tags=["Bot Control"])
async def stop_bot(uid: str = Depends(get_current_user)):
    logger.info(f"Received stop bot request for user: {uid}")
    db.collection("customers").document(uid).set({"personaConfig": {"isActive": False, "activePlatforms": []}}, merge=True)
    logger.info(f"Set isActive=false for user {uid}. Orchestrator will now take over.")
    return {"message": "Bot stop signal sent."}

@app.get("/api/connections", tags=["Bot Control"])
async def get_all_connections_status(uid: str = Depends(get_current_user)):
    logger.info(f"Fetching connection status for user: {uid}")
    doc = db.collection("customers").document(uid).get()
    if not doc.exists: return []
    persona_config = doc.to_dict().get("personaConfig", {})
    active_platforms = persona_config.get("activePlatforms", [])
    connections_ref = db.collection("customers").document(uid).collection("connections")
    status_list = []
    for platform in ["telegram", "discord", "slack"]:
        conn_doc = connections_ref.document(platform).get()
        is_connected = False
        if conn_doc.exists:
            data = conn_doc.to_dict()
            if platform == "telegram": is_connected = is_telegram_connection_valid(data)
            elif platform == "slack": is_connected = is_slack_connection_valid(data)
            elif platform == "discord": is_connected = is_discord_connection_valid(data)
        status_list.append({"platform": platform, "isConnected": is_connected, "isActiveNow": platform in active_platforms})
    return status_list

@app.get("/api/connections/telegram", tags=["Platform Connections"])
async def get_telegram_settings(uid: str = Depends(get_current_user)):
    logger.info(f"Fetching Telegram settings for user: {uid}")
    doc = db.collection("customers").document(uid).collection("connections").document("telegram").get()
    return doc.to_dict() if doc.exists else {}

@app.put("/api/connections/telegram", tags=["Platform Connections"])
async def save_telegram_settings(request: dict, uid: str = Depends(get_current_user)):
    logger.info(f"Saving Telegram settings for user: {uid}")
    db.collection("customers").document(uid).collection("connections").document("telegram").set(request, merge=True)
    return {"message": "Telegram settings saved."}

@app.post("/api/connections/telegram/start_auth", tags=["Platform Connections"])
async def telegram_connection_start(request: TelegramStartRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Starting Telegram auth for user {uid} with phone {request.phone_number}")
    try:
        client = TelegramClient(StringSession(), int(request.api_id), request.api_hash)
        await client.connect()
        await client.send_code_request(request.phone_number)
        connection_manager.add_client(uid, client)
        return {"status": "code_needed"}
    except Exception as e:
        logger.error(f"Telegram connection failed for user {uid}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Telegram connection failed: {str(e)}")

@app.post("/api/connections/telegram/submit_code", tags=["Platform Connections"])
async def telegram_connection_submit_code(request: TelegramCodeRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Submitting Telegram auth code for user {uid}")
    client = connection_manager.get_client(uid)
    if not client: raise HTTPException(status_code=408, detail="Connection timed out or invalid state.")
    try:
        await client.sign_in(code=request.code)
        final_data = await _finalize_telegram_connection(client)
        connection_manager.remove_client(uid)
        logger.info(f"Telegram code accepted for user {uid}. Connection successful.")
        return final_data
    except SessionPasswordNeededError:
        logger.info(f"Telegram 2FA password needed for user {uid}.")
        return {"status": "password_needed"}
    except Exception as e:
        logger.error(f"Failed to submit Telegram code for user {uid}", exc_info=True)
        if client.is_connected(): await client.disconnect()
        connection_manager.remove_client(uid)
        raise HTTPException(status_code=400, detail=f"Failed to submit code: {str(e)}")

@app.post("/api/connections/telegram/submit_password", tags=["Platform Connections"])
async def telegram_connection_submit_password(request: TelegramPasswordRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Submitting Telegram 2FA password for user {uid}")
    client = connection_manager.get_client(uid)
    if not client: raise HTTPException(status_code=408, detail="Connection timed out or invalid state.")
    try:
        await client.sign_in(password=request.password)
        final_data = await _finalize_telegram_connection(client)
        connection_manager.remove_client(uid)
        logger.info(f"Telegram 2FA password accepted for user {uid}. Connection successful.")
        return final_data
    except Exception as e:
        logger.error(f"Failed to sign in with Telegram password for user {uid}", exc_info=True)
        if client.is_connected(): await client.disconnect()
        connection_manager.remove_client(uid)
        raise HTTPException(status_code=400, detail=f"Failed to sign in: {str(e)}")

@app.put("/api/connections/slack", tags=["Platform Connections"])
async def save_slack_connection(request: SlackConnectionRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Saving Slack connection for user: {uid}")
    if not request.bot_token.startswith("xoxb-"): raise HTTPException(status_code=400, detail="Invalid Slack Bot Token.")
    if not request.app_token.startswith("xapp-"): raise HTTPException(status_code=400, detail="Invalid Slack App Token.")
    encrypted_bot_token = fernet.encrypt(request.bot_token.encode()).decode()
    encrypted_app_token = fernet.encrypt(request.app_token.encode()).decode()
    doc_ref = db.collection("customers").document(uid).collection("connections").document("slack")
    doc_ref.set({"bot_token_encrypted": encrypted_bot_token, "app_token_encrypted": encrypted_app_token, "channel_id": request.channel_id})
    return {"message": "Slack connected."}

@app.put("/api/connections/discord", tags=["Platform Connections"])
async def save_discord_connection(request: DiscordConnectionRequest, uid: str = Depends(get_current_user)):
    logger.info(f"Saving Discord connection for user: {uid}")
    encrypted_bot_token = fernet.encrypt(request.bot_token.encode()).decode()
    doc_ref = db.collection("customers").document(uid).collection("connections").document("discord")
    doc_ref.set({"bot_token_encrypted": encrypted_bot_token, "channel_id": request.channel_id})
    return {"message": "Discord connected."}