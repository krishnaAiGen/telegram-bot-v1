# src/config/settings.py
import os
from dotenv import load_dotenv

def load_server_config() -> dict:
    """
    Loads SERVER-LEVEL configuration from the .env file.

    This function is now stateless and only loads configuration necessary for the
    main orchestrator service to run, such as its own database credentials.

    It no longer loads any user-specific or bot-specific settings.
    """
    # Navigate up from src/config to the project root to find the .env file
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    dotenv_path = os.path.join(project_root, '.env')
    
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path, override=True)
    else:
        print(f"Warning: .env file not found at {dotenv_path}. Relying on environment variables.")

    # These are the only two truly global, server-level settings we need.
    # The Firebase path is for the server's own admin access.
    # The SECRET_KEY is for the server to encrypt/decrypt all user credentials.
    config = {
        "firebase_cred_path": os.getenv("FIREBASE_CRED_PATH"),
        "secret_key": os.getenv("SECRET_KEY"),
    }

    # Basic validation for server-critical settings
    if not config["firebase_cred_path"]:
        raise ValueError("CRITICAL: FIREBASE_CRED_PATH is not set in the environment.")
    if not config["secret_key"]:
        raise ValueError("CRITICAL: SECRET_KEY is not set in the environment for encryption.")

    print("Server configuration loaded successfully.")
    return config