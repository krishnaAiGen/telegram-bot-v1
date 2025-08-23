# backend/main.py
import sys
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# This line is CRITICAL. It adds the project's root directory to Python's
# path, allowing us to import from `config`, `persona_management`, etc.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import project modules
import config.settings # This executes your settings file, loading the .env
from backend.firebase_config import db
from firebase_admin import firestore
from backend.persona_generator import generate_personas_from_goal

app = FastAPI(title="Persona Management API")

# Add CORS middleware to allow the frontend to communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, restrict this to your frontend's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerationRequest(BaseModel):
    goal: str

@app.post("/generate-personas/")
async def create_personas_endpoint(request: GenerationRequest):
    try:
        personas_list = await generate_personas_from_goal(request.goal)
        if not personas_list:
            raise ValueError("Persona generation failed or returned an empty result.")

        doc_ref = db.collection("persona_teams").document()
        doc_ref.set({"personas": personas_list, "createdAt": firestore.SERVER_TIMESTAMP})
        return {"message": "Personas generated and saved successfully!", "doc_id": doc_ref.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/get-latest-personas/")
async def get_latest_personas_endpoint():
    try:
        query = db.collection("persona_teams").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(1)
        results = list(query.stream())
        if not results:
            return [] # Return an empty list if there's no data
        return results[0].to_dict().get("personas", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch personas: {e}")