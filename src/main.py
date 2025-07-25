# src/main.py

import asyncio
import os
import traceback
from telethon import TelegramClient
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
import discord

# Import configurations and managers
from config.settings import APP_CONFIG, TELEGRAM_USERS
from src.services.state_manager import StateManager
from src.core_logic.llm_personas import PersonaManager
import firebase_admin
from firebase_admin import credentials, firestore

# Import all modular components
from src.listeners.telegram_listener import setup_telegram_listener
from src.listeners.slack_listener import slack_listener_worker
from src.listeners.discord_listener import setup_discord_listener
from src.senders.telegram_sender import telegram_sender_worker
from src.senders.slack_sender import slack_sender_worker
from src.senders.discord_sender import discord_sender_worker
from src.workers.brain import brain_worker
from src.workers.scheduler import scheduler_worker

async def main():
    """
    Initializes and runs all components of the bot following the correct
    Telethon startup and execution lifecycle.
    """
    print("[MAIN] Initializing application...")
    brain_queue = asyncio.Queue()
    sender_queues = {
        "telegram_sender_queue": asyncio.Queue(),
        "slack_sender_queue": asyncio.Queue(),
        "discord_sender_queue": asyncio.Queue(),
    }
    
    
    if not firebase_admin._apps:
        cred = credentials.Certificate(APP_CONFIG['firebase_cred_path'])
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    state_manager = StateManager(db)
    persona_manager = PersonaManager()
    
    # --- 2. PLATFORM CLIENTS INITIALIZATION ---

    
    # Create all Telegram client objects
    ingestor_client = None
    sender_clients = {}
    all_telegram_clients = []
    if APP_CONFIG.get("ingestor_bot_user") and APP_CONFIG.get("sender_bot_users"):
        ingestor_user = APP_CONFIG['ingestor_bot_user']
        sender_users = APP_CONFIG['sender_bot_users']
        ingestor_client = TelegramClient(os.path.join(APP_CONFIG['data_dir'], ingestor_user), int(TELEGRAM_USERS[ingestor_user]['api_id']), TELEGRAM_USERS[ingestor_user]['api_hash'])
        sender_clients = {u: TelegramClient(os.path.join(APP_CONFIG['data_dir'], u), int(TELEGRAM_USERS[u]['api_id']), TELEGRAM_USERS[u]['api_hash']) for u in sender_users}
        all_telegram_clients = [ingestor_client] + list(sender_clients.values())
    
    # Slack Client
    slack_app = None
    slack_web_client = None
    slack_socket_handler = None
    if APP_CONFIG.get("slack_bot_token") and APP_CONFIG.get("slack_app_token"):
        slack_app = AsyncApp(token=APP_CONFIG['slack_bot_token'])
        slack_web_client = slack_app.client
        slack_socket_handler = AsyncSocketModeHandler(slack_app, APP_CONFIG['slack_app_token'])
    
    
    discord_client = None
    if APP_CONFIG.get("discord_bot_token"):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        discord_client = discord.Client(intents=intents)

    
    
    # --- 3. BOT LIFECYCLE MANAGEMENT ---
    try:
        # --- CONNECT CLIENTS (SEQUENTIALLY) ---
        if all_telegram_clients:
            print("[MAIN] Connecting and authorizing all Telegram clients...")
            for client in all_telegram_clients:
                await client.start()
                if not await client.is_user_authorized():
                    raise Exception(f"Telegram client for session '{client.session.filename}' is not authorized.")
            print("[MAIN] All Telegram clients connected and authorized.")
        
        # --- LAUNCH ALL WORKERS (CONCURRENTLY) ---
        print("[MAIN] Launching all background workers...")
        async with asyncio.TaskGroup() as tg:
            
            # --- START LONG-RUNNING CLIENTS ---
            if slack_socket_handler:
                tg.create_task(slack_socket_handler.start_async())
            if discord_client:
                tg.create_task(discord_client.start(APP_CONFIG['discord_bot_token']))
            for client in all_telegram_clients:
                tg.create_task(client.run_until_disconnected())

            # --- START LISTENERS ---
            if ingestor_client and APP_CONFIG.get("telegram_group_id"):
                setup_telegram_listener(ingestor_client, brain_queue, APP_CONFIG['telegram_group_id'])
            if slack_app and APP_CONFIG.get("slack_channel_id"):
                tg.create_task(slack_listener_worker(slack_app, brain_queue, APP_CONFIG['slack_channel_id']))
            if discord_client and APP_CONFIG.get("discord_channel_id"):
                setup_discord_listener(discord_client, brain_queue, APP_CONFIG['discord_channel_id'])
                
            # --- START CORE & SENDER WORKERS ---
            tg.create_task(brain_worker(brain_queue, sender_queues, persona_manager, state_manager, db))
            tg.create_task(scheduler_worker(sender_queues, persona_manager, state_manager, db))
            tg.create_task(telegram_sender_worker(sender_queues["telegram_sender_queue"], sender_clients))
            tg.create_task(slack_sender_worker(sender_queues["slack_sender_queue"], slack_web_client))
            tg.create_task(discord_sender_worker(sender_queues["discord_sender_queue"], discord_client))

            print("--- Bot is fully operational on configured platforms. Press Ctrl+C to stop. ---")

    except* Exception as eg:
        print(f"--- Main task group encountered errors: ---")
        for exc in eg.exceptions:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
    finally:
        # --- GRACEFUL SHUTDOWN ---
        print("[MAIN] Shutting down...")
        if all_telegram_clients:
            for client in all_telegram_clients:
                if client.is_connected():
                    await client.disconnect()
        if discord_client and discord_client.is_ready():
            await discord_client.close()
        print("[MAIN] All clients disconnected. Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n[MAIN] Shutdown requested by user.")