# config/settings.py
import json
import os
from dotenv import load_dotenv

project_root = os.path.join(os.path.dirname(__file__), '..')
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

def load_characters_config(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CRITICAL: Character file not found at '{file_path}'.")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"CRITICAL: Character file at '{file_path}' is not valid JSON.")

CHARACTERS_FILE_PATH = os.path.join(os.path.dirname(__file__), 'characters.json')
CHARACTERS_DATA = load_characters_config(CHARACTERS_FILE_PATH)

APP_CONFIG = {
    "openai_api_key": os.getenv("OPENAI_API_KEY"),
    "firebase_cred_path": os.getenv("FIREBASE_CRED_PATH"),
    "telegram_group_id": int(os.getenv("TELEGRAM_GROUP_ID", 0)),
    "data_dir": os.path.join(project_root, 'data'),
    "ingestor_bot_user": os.getenv("INGESTOR_BOT_USER"),
    "sender_bot_users": [user.strip() for user in os.getenv("SENDER_BOT_USERS", "").split(',') if user.strip()],
    "known_bot_ids": [int(bot_id) for bot_id in os.getenv("KNOWN_BOT_IDS", "").split(',') if bot_id.isdigit()],
    "min_initiate_hours": float(os.getenv("MIN_INITIATE_HOURS", 1.0)),
    "min_send_delay_secs": float(os.getenv("MIN_SEND_DELAY_SECS", 5.0)),
    "max_send_delay_secs": float(os.getenv("MAX_SEND_DELAY_SECS", 15.0)),
    "random_response_rate": float(os.getenv("RANDOM_RESPONSE_RATE", 1.0)),
    "xai_api_key": os.getenv("X_API_KEY"),
    "triage_model": os.getenv("TRIAGE_MODEL", "gpt-3.5-turbo"),
    "response_context_messages": int(os.getenv("RESPONSE_CONTEXT_MESSAGES",4)),
    "link_post_cooldown_mins": int(os.getenv("LINK_POST_COOLDOWN_MINS", 15)),
    "slack_bot_token": os.getenv("SLACK_BOT_TOKEN"),
    "slack_app_token": os.getenv("SLACK_APP_TOKEN"),
    "slack_channel_id": os.getenv("SLACK_CHANNEL_ID"),
}

TELEGRAM_USERS = {}
all_bot_usernames = [APP_CONFIG["ingestor_bot_user"]] + APP_CONFIG["sender_bot_users"]

for username in set(filter(None, all_bot_usernames)):
    env_var_prefix = f"TELEGRAM_USER_{username}_"
    api_id = os.getenv(f"{env_var_prefix}API_ID")
    api_hash = os.getenv(f"{env_var_prefix}API_HASH")
    if api_id and api_hash:
        TELEGRAM_USERS[username] = {"api_id": api_id, "api_hash": api_hash}
    else:
        print(f"Warning: Missing API credentials for Telegram user: {username}")

if not APP_CONFIG["openai_api_key"]:
    raise ValueError("CRITICAL: OPENAI_API_KEY is not set in the .env file.")
if not APP_CONFIG["ingestor_bot_user"] or not APP_CONFIG["sender_bot_users"]:
    raise ValueError("CRITICAL: INGESTOR_BOT_USER and SENDER_BOT_USERS must be set in .env")
if not APP_CONFIG["slack_bot_token"] or not APP_CONFIG["slack_app_token"]:
    raise ValueError("CRITICAL: SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set in .env")

if APP_CONFIG["ingestor_bot_user"] not in TELEGRAM_USERS:
    raise ValueError(f"CRITICAL: Credentials for ingestor '{APP_CONFIG['ingestor_bot_user']}' are missing.")
for user in APP_CONFIG["sender_bot_users"]:
    if user not in TELEGRAM_USERS:
        raise ValueError(f"CRITICAL: Credentials for sender '{user}' are missing.")

print("Configuration loaded successfully.")