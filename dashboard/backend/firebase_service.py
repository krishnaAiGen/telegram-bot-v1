# dashboard/backend/firebase_service.py

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from typing import List, Dict, Any, Optional
import os
import sys

# Add the project root to Python path for imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from config.settings import APP_CONFIG

class FirebaseService:
    def __init__(self):
        # Initialize Firebase if not already initialized
        if not firebase_admin._apps:
            try:
                cred = credentials.Certificate(APP_CONFIG['firebase_cred_path'])
                firebase_admin.initialize_app(cred)
                print("[Firebase] Successfully initialized Firebase Admin SDK")
            except Exception as e:
                print(f"[Firebase] CRITICAL ERROR: Failed to initialize Firebase. Error: {e}")
                raise e
        
        self.db = firestore.client()
    
    async def store_pipeline_run(self, pipeline_data: Dict[str, Any]) -> str:
        """
        Store a pipeline run in Firebase and return the document ID
        """
        try:
            doc_ref = self.db.collection('pipeline_runs').document()
            doc_ref.set(pipeline_data)
            print(f"[Firebase] Stored pipeline run: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            print(f"[Firebase] Error storing pipeline run: {e}")
            raise e
    
    async def store_persona(self, persona_data: Dict[str, Any]) -> str:
        """
        Store a persona in Firebase and return the document ID
        """
        try:
            doc_ref = self.db.collection('personas').document()
            doc_ref.set(persona_data)
            print(f"[Firebase] Stored persona: {persona_data.get('persona_name', 'Unknown')}")
            return doc_ref.id
        except Exception as e:
            print(f"[Firebase] Error storing persona: {e}")
            raise e
    
    async def get_user_personas(self, user_email: str) -> List[Dict[str, Any]]:
        """
        Get all personas for a specific user
        """
        try:
            personas_ref = self.db.collection('personas')
            query = personas_ref.where('user_email', '==', user_email).order_by('created_at', direction=firestore.Query.DESCENDING)
            docs = query.stream()
            
            personas = []
            for doc in docs:
                persona_data = doc.to_dict()
                persona_data['id'] = doc.id
                personas.append(persona_data)
            
            print(f"[Firebase] Retrieved {len(personas)} personas for user: {user_email}")
            return personas
        except Exception as e:
            print(f"[Firebase] Error getting user personas: {e}")
            raise e
    
    async def get_user_pipeline_runs(self, user_email: str) -> List[Dict[str, Any]]:
        """
        Get all pipeline runs for a specific user
        """
        try:
            runs_ref = self.db.collection('pipeline_runs')
            query = runs_ref.where('user_email', '==', user_email).order_by('created_at', direction=firestore.Query.DESCENDING)
            docs = query.stream()
            
            runs = []
            for doc in docs:
                run_data = doc.to_dict()
                run_data['id'] = doc.id
                runs.append(run_data)
            
            print(f"[Firebase] Retrieved {len(runs)} pipeline runs for user: {user_email}")
            return runs
        except Exception as e:
            print(f"[Firebase] Error getting user pipeline runs: {e}")
            raise e
    
    async def delete_persona(self, persona_id: str, user_email: str) -> bool:
        """
        Delete a persona (with user verification)
        """
        try:
            doc_ref = self.db.collection('personas').document(persona_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return False
            
            # Verify the persona belongs to the user
            if doc.to_dict().get('user_email') != user_email:
                return False
            
            doc_ref.delete()
            print(f"[Firebase] Deleted persona: {persona_id}")
            return True
        except Exception as e:
            print(f"[Firebase] Error deleting persona: {e}")
            raise e
    
    async def update_persona(self, persona_id: str, user_email: str, updates: Dict[str, Any]) -> bool:
        """
        Update a persona (with user verification)
        """
        try:
            doc_ref = self.db.collection('personas').document(persona_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return False
            
            # Verify the persona belongs to the user
            if doc.to_dict().get('user_email') != user_email:
                return False
            
            updates['updated_at'] = datetime.utcnow().isoformat()
            doc_ref.update(updates)
            print(f"[Firebase] Updated persona: {persona_id}")
            return True
        except Exception as e:
            print(f"[Firebase] Error updating persona: {e}")
            raise e