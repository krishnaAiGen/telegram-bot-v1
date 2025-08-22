# dashboard/backend/main.py

import sys
import os
import uuid
import importlib.util
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
import firebase_admin
from firebase_admin import credentials, firestore
# --- 1. Project Path Setup ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- 2. Import All Necessary Modules ---
from config.settings import APP_CONFIG

# Import the persona pipeline function
# We need to handle the hyphen in the folder name and relative imports
def import_persona_pipeline():
    """Import the persona pipeline function handling relative imports."""
    import importlib.util
    import types
    
    # Create a module for persona-management
    persona_management_path = os.path.join(project_root, 'persona-management')
    
    # First, we need to import all the dependencies
    # Import schemas
    schemas_path = os.path.join(persona_management_path, 'schemas')
    
    # Import pipeline_state
    pipeline_state_file = os.path.join(schemas_path, 'pipeline_state.py')
    spec = importlib.util.spec_from_file_location("pipeline_state", pipeline_state_file)
    pipeline_state_module = importlib.util.module_from_spec(spec)
    
    # Import persona_profile  
    persona_profile_file = os.path.join(schemas_path, 'persona_profile.py')
    spec2 = importlib.util.spec_from_file_location("persona_profile", persona_profile_file)
    persona_profile_module = importlib.util.module_from_spec(spec2)
    
    # Execute the modules
    spec.loader.exec_module(pipeline_state_module)
    spec2.loader.exec_module(persona_profile_module)
    
    # Add to sys.modules so relative imports work
    sys.modules['schemas.pipeline_state'] = pipeline_state_module
    sys.modules['schemas.persona_profile'] = persona_profile_module
    
    # Now import the pipeline
    pipeline_file = os.path.join(persona_management_path, 'pipeline.py')
    spec3 = importlib.util.spec_from_file_location("pipeline", pipeline_file)
    pipeline_module = importlib.util.module_from_spec(spec3)
    
    # Set up the module's __package__ to handle relative imports
    pipeline_module.__package__ = 'persona_management'
    
    # Add the schemas to the pipeline module's namespace
    pipeline_module.PipelineState = pipeline_state_module.PipelineState
    pipeline_module.Persona = persona_profile_module.Persona
    
    spec3.loader.exec_module(pipeline_module)
    
    return pipeline_module.run_persona_factory_pipeline

# Import the function
run_persona_factory_pipeline = import_persona_pipeline()

# Imports from our new auth module
from .auth import (get_password_hash, verify_password, create_access_token, verify_token)


# --- 3. Firebase Initialization ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(APP_CONFIG['firebase_cred_path'])
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to initialize Firebase. Check your FIREBASE_CRED_PATH. Error: {e}")
        exit()
db = firestore.client()


# --- 4. FastAPI Application Setup ---
app = FastAPI(title="AI Persona Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (frontend)
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- 5. Pydantic Models for Data Validation ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class GoalPrompt(BaseModel):
    goal: str

class PersonaConfig(BaseModel):
    characters: list[dict]

# --- 6. Authentication Dependency ---
async def get_current_user_id(token: str = Depends(oauth2_scheme)):
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return user_id

# --- 7. API Endpoints ---

@app.post("/signup", status_code=201)
async def signup(user: UserCreate):
    users_ref = db.collection("dashboard_users")
    if any(users_ref.where("email", "==", user.email).stream()):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user.password)
    
    users_ref.document(user_id).set({
        "email": user.email,
        "hashed_password": hashed_password,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "personaConfig": {"characters": []},
        "personaLibrary": {}
    })
    return {"message": "Account created successfully. Please log in."}

@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    users_ref = db.collection("dashboard_users")
    docs = list(users_ref.where("email", "==", form_data.username).stream())
    if not docs:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    user_doc = docs[0]
    user_data = user_doc.to_dict()
    
    if not verify_password(form_data.password, user_data.get("hashed_password")):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    access_token = create_access_token(data={"sub": user_doc.id})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/generate-personas")
async def generate_personas(prompt: GoalPrompt, user_id: str = Depends(get_current_user_id)):
    """
    Runs the Persona Factory pipeline and returns the generated personas.
    Also stores the results in Firebase for history tracking.
    """
    print(f"--- [User: {user_id}] Starting Persona Factory Pipeline ---")
    print(f"--- Goal: {prompt.goal} ---")
    
    try:
        # Run the actual persona factory pipeline
        result = await run_persona_factory_pipeline(prompt.goal)
        
        if result.get("status") == "success":
            # Get user email for Firebase storage
            user_doc = db.collection("dashboard_users").document(user_id).get()
            user_email = user_doc.to_dict().get("email", "unknown") if user_doc.exists else "unknown"
            
            # Store pipeline run in Firebase
            pipeline_run_data = {
                "user_id": user_id,
                "user_email": user_email,
                "goal": prompt.goal,
                "result": result,
                "created_at": firestore.SERVER_TIMESTAMP,
                "status": "success",
                "persona_count": len(result.get("personas", []))
            }
            
            pipeline_run_ref = db.collection("pipeline_runs").document()
            pipeline_run_ref.set(pipeline_run_data)
            pipeline_run_id = pipeline_run_ref.id
            
            # Store individual personas in Firebase
            for i, persona in enumerate(result.get("personas", [])):
                persona_data = {
                    **persona,
                    "user_id": user_id,
                    "user_email": user_email,
                    "pipeline_run_id": pipeline_run_id,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "persona_index": i
                }
                db.collection("personas").document().set(persona_data)
            
            print(f"--- [User: {user_id}] Successfully generated {len(result.get('personas', []))} personas ---")
            
            # Add the pipeline run ID to the response
            result["pipeline_run_id"] = pipeline_run_id
            return result
            
        else:
            # Store failed pipeline run
            user_doc = db.collection("dashboard_users").document(user_id).get()
            user_email = user_doc.to_dict().get("email", "unknown") if user_doc.exists else "unknown"
            
            pipeline_run_data = {
                "user_id": user_id,
                "user_email": user_email,
                "goal": prompt.goal,
                "error": result.get("reason", "Unknown error"),
                "created_at": firestore.SERVER_TIMESTAMP,
                "status": "failed"
            }
            
            db.collection("pipeline_runs").document().set(pipeline_run_data)
            
            raise HTTPException(status_code=500, detail=result.get("reason", "Persona generation failed."))
            
    except Exception as e:
        print(f"ERROR during persona generation for user {user_id}: {e}")
        
        # Store failed pipeline run
        try:
            user_doc = db.collection("dashboard_users").document(user_id).get()
            user_email = user_doc.to_dict().get("email", "unknown") if user_doc.exists else "unknown"
            
            pipeline_run_data = {
                "user_id": user_id,
                "user_email": user_email,
                "goal": prompt.goal,
                "error": str(e),
                "created_at": firestore.SERVER_TIMESTAMP,
                "status": "failed"
            }
            
            db.collection("pipeline_runs").document().set(pipeline_run_data)
        except:
            pass  # Don't fail the main error if logging fails
        
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.get("/personas")
async def get_personas(user_id: str = Depends(get_current_user_id)):
    """Fetches the user's currently SAVED persona configuration."""
    doc_ref = db.collection("dashboard_users").document(user_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    return doc.to_dict().get("personaConfig", {"characters": []})

@app.get("/personas/library")
async def get_persona_library(user_id: str = Depends(get_current_user_id)):
    """Get all personas from user's library (Firebase collection)"""
    try:
        personas_ref = db.collection("personas")
        query = personas_ref.where("user_id", "==", user_id).order_by("created_at", direction=firestore.Query.DESCENDING)
        docs = query.stream()
        
        personas = []
        for doc in docs:
            persona_data = doc.to_dict()
            persona_data['id'] = doc.id
            # Convert Firestore timestamp to string if needed
            if 'created_at' in persona_data and hasattr(persona_data['created_at'], 'isoformat'):
                persona_data['created_at'] = persona_data['created_at'].isoformat()
            personas.append(persona_data)
        
        return {"personas": personas}
    except Exception as e:
        print(f"Error fetching persona library: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch persona library: {e}")

@app.get("/pipeline-runs")
async def get_pipeline_runs(user_id: str = Depends(get_current_user_id)):
    """Get pipeline run history for the user"""
    try:
        runs_ref = db.collection("pipeline_runs")
        query = runs_ref.where("user_id", "==", user_id).order_by("created_at", direction=firestore.Query.DESCENDING).limit(20)
        docs = query.stream()
        
        runs = []
        for doc in docs:
            run_data = doc.to_dict()
            run_data['id'] = doc.id
            # Convert Firestore timestamp to string if needed
            if 'created_at' in run_data and hasattr(run_data['created_at'], 'isoformat'):
                run_data['created_at'] = run_data['created_at'].isoformat()
            runs.append(run_data)
        
        return {"pipeline_runs": runs}
    except Exception as e:
        print(f"Error fetching pipeline runs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch pipeline runs: {e}")

@app.post("/personas")
async def save_personas(config: PersonaConfig, user_id: str = Depends(get_current_user_id)):
    """Saves the user's active team as their official persona configuration."""
    doc_ref = db.collection("dashboard_users").document(user_id)
    # The frontend sends the full { "characters": [...] } object
    doc_ref.set({"personaConfig": config.dict()}, merge=True)
    return {"message": "Persona team saved successfully"}

@app.get("/dashboard")
async def serve_dashboard():
    """Serve the frontend dashboard"""
    frontend_file = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(frontend_file):
        return FileResponse(frontend_file)
    else:
        raise HTTPException(status_code=404, detail="Dashboard frontend not found")