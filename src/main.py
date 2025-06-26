# src/main.py
import asyncio
import os
from telethon import TelegramClient, events

# Import configurations and managers
from config.settings import APP_CONFIG, TELEGRAM_USERS
from src.services.state_manager import StateManager
from src.core_logic.llm_personas import PersonaManager
import firebase_admin
from firebase_admin import credentials, firestore

# Import the refactored worker functions
from src.workers.listener import listener_handler
from src.workers.brain import brain_worker
from src.workers.sender import sender_worker
from src.workers.scheduler import scheduler_worker

async def main():
    """
    Initializes and runs all components of the bot: clients, database,
    and background workers for listening, thinking, sending, and scheduling.
    """
    print("[MAIN] Initializing application...")
    brain_queue, sender_queue = asyncio.Queue(), asyncio.Queue()
    state_manager, persona_manager = StateManager(), PersonaManager()
    
    if not firebase_admin._apps:
        cred = credentials.Certificate(APP_CONFIG['firebase_cred_path'])
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    ingestor_user, sender_users = APP_CONFIG['ingestor_bot_user'], APP_CONFIG['sender_bot_users']
    
    # Create client instances
    ingestor_client = TelegramClient(os.path.join(APP_CONFIG['data_dir'], ingestor_user), int(TELEGRAM_USERS[ingestor_user]['api_id']), TELEGRAM_USERS[ingestor_user]['api_hash'])
    sender_clients = {u: TelegramClient(os.path.join(APP_CONFIG['data_dir'], u), int(TELEGRAM_USERS[u]['api_id']), TELEGRAM_USERS[u]['api_hash']) for u in sender_users}
    all_clients = [ingestor_client] + list(sender_clients.values())

    # Attach the event handler
    ingestor_client.add_event_handler(lambda e: listener_handler(e, brain_queue), events.NewMessage(chats=[APP_CONFIG['telegram_group_id']]))
    
    print("[MAIN] Connecting clients...")
    
    # Start and connect all telegram clients first
    print("[MAIN] Starting all Telegram clients...")
    for client in all_clients:
        await client.connect()    
        if not await client.is_user_authorized():
            if client.session and hasattr(client.session, "filename"):
                session_name = os.path.basename(str(client.session.filename))
            else:
                session_name = "unknown"
            raise Exception(f"Client for session '{session_name}' is not authorized.")

    # Start the background workers
    print("[MAIN] Launching background workers...")
    tasks = []
    tasks.append(asyncio.create_task(brain_worker(brain_queue, sender_queue, persona_manager, state_manager, db)))
    tasks.append(asyncio.create_task(sender_worker(sender_queue, sender_clients)))
    tasks.append(asyncio.create_task(scheduler_worker(sender_queue, persona_manager, state_manager, db)))
    
    # Add client tasks
    valid_clients = [
        c for c in all_clients
        if c is not None and hasattr(c, "run_until_disconnected") and callable(c.run_until_disconnected)
    ]
    
    for client in valid_clients:
        tasks.append(asyncio.create_task(client.run_until_disconnected()))
    
    print("--- Bot is fully operational. Press Ctrl+C to stop. ---")
    
    # Run all tasks concurrently
    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        print(f"[MAIN] Error in main tasks: {e}")
        # Cancel all remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nBot shutting down gracefully.")
    except Exception as e:
        print(f"FATAL: An unhandled error occurred in main: {e}")