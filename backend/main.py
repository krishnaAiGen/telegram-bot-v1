# backend/main.py
import os
import requests
import time
import pydantic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, RootModel
import firebase_admin
from firebase_admin import credentials, auth, firestore
from dotenv import load_dotenv
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cryptography.fernet import Fernet

from persona_management.pipeline import run_persona_factory_pipeline

from backend.persona_generator import generate_personas_from_goal

# --- Initialization ---
# Load environment variables from .env file
load_dotenv()

# Initialize Firebase Admin SDK
# Make sure 'data/firebase-credentials.json' path is correct relative to your project root
cred_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'firebase-credentials.json')
if not os.path.exists(cred_path):
    raise FileNotFoundError(f"Firebase credentials not found at {cred_path}")
cred = credentials.Certificate(cred_path)
firebase_app = firebase_admin.initialize_app(cred)

# Initialize FastAPI App
app = FastAPI(title="AI Persona Bot Backend API")

# --- CORS Middleware ---
# This is kept to allow your frontend to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, restrict this to your frontend's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set in .env file for encryption.")
fernet = Fernet(SECRET_KEY.encode())

# --- Pydantic Models for Data Validation ---
class UserCredentials(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    idToken: str  # This is the JWT from Firebase
    email: EmailStr
# --- ADD these new Pydantic Models ---
class ConnectionKeyRequest(BaseModel):
    api_key: str

class ConnectionStatusResponse(BaseModel):
    has_openai_key: bool
    
class GenerationRequest(BaseModel):
    goal: str
    
class DraftUpdateRequest(BaseModel):
    activeTeam: list
# --- Security Dependency ---
security = HTTPBearer()

# The NEW, correct version
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validates the Firebase ID token and returns the user's UID string."""
    try:
        id_token = credentials.credentials
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token['uid'] # <--- FIX: We return ONLY the 'uid' string
    except Exception as e:
        # It's also good practice to convert the exception to a string for safety
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")


# --- Authentication Endpoints ---

@app.post("/auth/register", status_code=201, tags=["Authentication"])
async def register(credentials: UserCredentials):
    """Creates a new user in Firebase Authentication."""
    try:
        user = auth.create_user(
            email=credentials.email,
            password=credentials.password
        )
        # We should also create their initial document in Firestore here
        db = firestore.client()
        user_doc_ref = db.collection("customers").document(user.uid)
        user_doc_ref.set({
            "email": user.email,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "personaConfig": {
                "draftTeam": {},
                "liveTeam": {}
            }
        })
        return {"message": "User created successfully and database entry initialized.", "uid": user.uid}
    except auth.EmailAlreadyExistsError:
        raise HTTPException(
            status_code=409,  # 409 Conflict
            detail=f"User with email {credentials.email} already exists."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
async def login(credentials: UserCredentials):
    """Authenticates a user and returns a Firebase ID token (JWT)."""
    firebase_api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not firebase_api_key:
        raise HTTPException(status_code=500, detail="Firebase Web API Key not configured in .env file.")

    rest_api_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
    
    payload = {
        "email": credentials.email,
        "password": credentials.password,
        "returnSecureToken": True
    }

    try:
        response = requests.post(rest_api_url, json=payload)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        
        data = response.json()
        return AuthResponse(idToken=data['idToken'], email=data['email'])

    except requests.exceptions.HTTPError as err:
        error_detail = err.response.json().get("error", {}).get("message", "Invalid credentials.")
        raise HTTPException(
            status_code=401,  # 401 Unauthorized
            detail=error_detail
        )
        
        
# --- ADD these two new SECURE endpoints ---
@app.post("/api/connections/openai", status_code=201, tags=["Connections"])
async def save_openai_key(request: ConnectionKeyRequest, uid: str = Depends(get_current_user)):
    """Saves and encrypts the user's OpenAI API key."""
    try:
        db = firestore.client()
        # Encrypt the key before storing
        encrypted_key = fernet.encrypt(request.api_key.encode()).decode()

        # We will use a subcollection for connections for better organization
        connections_ref = db.collection("customers").document(uid).collection("connections").document("openai")
        connections_ref.set({
            "encrypted_key": encrypted_key,
            "lastUpdated": firestore.SERVER_TIMESTAMP
        })
        return {"message": "OpenAI key saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save key: {str(e)}")


@app.get("/api/connections/status", response_model=ConnectionStatusResponse, tags=["Connections"])
async def get_connection_status(uid: str = Depends(get_current_user)):
    """Checks if the user has already provided an OpenAI key."""
    try:
        db = firestore.client()
        doc_ref = db.collection("customers").document(uid).collection("connections").document("openai")
        doc = doc_ref.get()
        return ConnectionStatusResponse(has_openai_key=doc.exists)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check status: {str(e)}")

# Add this new, secure endpoint to backend/main.py

# In backend/main.py

@app.post("/api/personas/generate", tags=["Persona Generation"])
async def generate_personas(request: GenerationRequest, uid: str = Depends(get_current_user)):
    """
    Generates a new team of personas using the user's goal and their stored
    OpenAI key, then saves the result to their draftTeam.
    """
    db = firestore.client()
    
    # 1. Fetch and decrypt the user's OpenAI key
    try:
        doc_ref = db.collection("customers").document(uid).collection("connections").document("openai")
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=400, detail="OpenAI API key not found for user.")
        
        encrypted_key = doc.to_dict().get("encrypted_key")
        decrypted_key = fernet.decrypt(encrypted_key.encode()).decode()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not retrieve or decrypt API key: {str(e)}")

    # 2. Run the persona generation pipeline
    try:
        # We need to call the orchestrator with the api_key argument
        pipeline_result = await run_persona_factory_pipeline(
            initial_prompt=request.goal,
            api_key=decrypted_key
        )
        if pipeline_result.get("status") != "success":
             raise RuntimeError(pipeline_result.get("reason", "Unknown pipeline failure"))

        generated_personas = pipeline_result.get("personas", [])
        if not generated_personas:
            raise HTTPException(status_code=500, detail="Persona generation succeeded but produced no personas.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during persona generation: {str(e)}")

    # 3. Save the result to the user's draftTeam in Firestore
    try:
        user_doc_ref = db.collection("customers").document(uid)
        
        # --- THIS IS THE FIX ---
        # Generate a timestamp using Python's time module
        current_timestamp = int(time.time())
        for i, persona in enumerate(generated_personas):
            # Use the Python timestamp to create a unique ID
            persona['id'] = f"draft_{current_timestamp}_{i}"
        # -----------------------

        user_doc_ref.set({
            "personaConfig": {
                "draftTeam": generated_personas,
                "lastUpdated": firestore.SERVER_TIMESTAMP # It's OK to use the placeholder here!
            }
        }, merge=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save generated personas: {str(e)}")

    return {"message": "Personas generated and saved to your draft successfully!", "personas": generated_personas}

@app.get("/api/draft", tags=["Persona Management"])
async def get_draft_team(uid: str = Depends(get_current_user)):
    """
    Fetches the current persona team from the user's draft.
    """
    try:
        db = firestore.client()
        doc_ref = db.collection("customers").document(uid)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            # Navigate through the map to get the draftTeam array
            persona_config = data.get("personaConfig", {})
            draft_team = persona_config.get("draftTeam", [])
            return draft_team
        else:
            # If the user document somehow doesn't exist, return an empty list
            return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch draft team: {str(e)}")

@app.put("/api/draft", status_code=200, tags=["Persona Management"])
async def update_draft_team(request: DraftUpdateRequest, uid: str = Depends(get_current_user)):
    """
    Overwrites the user's entire draftTeam with the provided data.
    This is used for saving edits, deletions, and reordering.
    """
    try:
        db = firestore.client()
        user_doc_ref = db.collection("customers").document(uid)
        
        # The actual data is in request.__root__ because of the Pydantic model
        updated_team = request.activeTeam

        user_doc_ref.set({
            "personaConfig": {
                "draftTeam": updated_team,
                "lastUpdated": firestore.SERVER_TIMESTAMP
            }
        }, merge=True) # merge=True ensures we don't overwrite other fields

        return {"message": "Draft saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save draft: {str(e)}")