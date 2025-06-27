# src/main.py
import asyncio
import os
import traceback
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
    Initializes and runs all components of the bot following the correct
    Telethon startup and execution lifecycle.
    """
    print("[MAIN] Initializing application...")
    brain_queue, sender_queue = asyncio.Queue(), asyncio.Queue()
    
    if not firebase_admin._apps:
        cred = credentials.Certificate(APP_CONFIG['firebase_cred_path'])
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    state_manager = StateManager(db)
    persona_manager = PersonaManager()
    
    # Create all Telegram client objects
    ingestor_user = APP_CONFIG['ingestor_bot_user']
    sender_users = APP_CONFIG['sender_bot_users']
    ingestor_client = TelegramClient(os.path.join(APP_CONFIG['data_dir'], ingestor_user), int(TELEGRAM_USERS[ingestor_user]['api_id']), TELEGRAM_USERS[ingestor_user]['api_hash'])
    sender_clients = {u: TelegramClient(os.path.join(APP_CONFIG['data_dir'], u), int(TELEGRAM_USERS[u]['api_id']), TELEGRAM_USERS[u]['api_hash']) for u in sender_users}
    all_clients = [ingestor_client] + list(sender_clients.values())

    # Attach the event handler to the listener client
    ingestor_client.add_event_handler(lambda e: listener_handler(e, brain_queue), events.NewMessage(chats=[APP_CONFIG['telegram_group_id']]))
    
<<<<<<< HEAD
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
=======
    # A list to hold all our running tasks for graceful shutdown
    tasks = []
    try:
        # --- CORRECT STARTUP PROCEDURE ---
        print("[MAIN] Starting all Telegram clients...")
        # 1. Start all clients first. This connects them.
        for client in all_clients:
            # The .start() method is awaitable and must be awaited.
            await client.start() # type: ignore
            if not await client.is_user_authorized():
                raise Exception(f"A client is not authorized. Please log in.")
        print("[MAIN] All clients connected and authorized.")
        # --- END OF CORRECT STARTUP ---
        
        print("[MAIN] Launching background workers...")
        # 2. Create the background tasks.
        tasks.append(asyncio.create_task(brain_worker(brain_queue, sender_queue, persona_manager, state_manager, db)))
        tasks.append(asyncio.create_task(sender_worker(sender_queue, sender_clients)))
        tasks.append(asyncio.create_task(scheduler_worker(sender_queue, persona_manager, state_manager, db)))
        
        print("--- Bot is fully operational. Press Ctrl+C to stop. ---")
        
        # 3. Wait for the primary listener client to disconnect.
        #    This keeps the script alive while the workers run in the background.
        await ingestor_client.run_until_disconnected()

    except Exception as e:
        print(f"\nFATAL: An unhandled exception occurred: {e}")
        traceback.print_exc()
    finally:
        # 4. Graceful shutdown procedure
        print("\n[MAIN] Shutting down...")
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # Disconnect all clients
        for client in all_clients:
            if client.is_connected():
                await client.disconnect() 
        
        print("[MAIN] Shutdown complete.")
>>>>>>> 7838f6b (Add JSON upload logic-integrate scheduler-improve the links logic)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n[MAIN] Keyboard interrupt detected.")