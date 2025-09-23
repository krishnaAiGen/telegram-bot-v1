# backend/firebase_config.py

import sys
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Add the project root to the path to allow importing from 'config'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the application configuration which has loaded the .env file
from config.settings import APP_CONFIG

# Check if the app is already initialized to prevent errors on reload
if not firebase_admin._apps:
    # Use credentials.Certificate() with the explicit path from your config
    cred_path = APP_CONFIG["firebase_cred_path"]
    cred = credentials.Certificate(cred_path)
    
    firebase_admin.initialize_app(cred)

# Get a reference to the Firestore database client
db = firestore.client()