# src/main.py
import asyncio
import os
import traceback
from telethon import TelegramClient
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler


# Import configurations and managers
from config.settings import APP_CONFIG, TELEGRAM_USERS
from src.services.state_manager import StateManager
from src.core_logic.llm_personas import PersonaManager
import firebase_admin
from firebase_admin import credentials, firestore

# Import our new, modular workers from their correct locations
from src.listener.telegram_listener import setup_telegram_listener
from src.listener.slack_listener import slack_listener_worker
from src.workers.brain import brain_worker
from src.workers.scheduler import scheduler_worker
from src.sender.telegram_sender import telegram_sender_worker
from src.sender.slack_sender import slack_sender_worker

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
    }
    
    
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
    
    # Slack Client
    slack_app = AsyncApp(token=APP_CONFIG['slack_bot_token'])
    slack_web_client = slack_app.client
    slack_socket_handler = AsyncSocketModeHandler(slack_app, APP_CONFIG['slack_app_token'])
    
    setup_telegram_listener(ingestor_client, brain_queue, APP_CONFIG['telegram_group_id'])
    
    print("[MAIN] Launching all background workers and connecting clients...")
    
    # Attach the event handler to the listener client
    #ingestor_client.add_event_handler(lambda e: listener_handler(e, brain_queue), events.NewMessage(chats=[APP_CONFIG['telegram_group_id']]))
    
    try:
        # Using a TaskGroup is a modern and safer way to manage concurrent tasks.
        # It automatically handles cancellation and waits for all tasks to finish.
        async with asyncio.TaskGroup() as tg:
            # --- 5. CREATE AND LAUNCH ALL TASKS ---
            
            # Start the long-running client connections
            tg.create_task(slack_socket_handler.start_async())
            for client in all_clients:
                tg.create_task(client.run_until_disconnected())

            # Start our custom workers
            tg.create_task(slack_listener_worker(slack_app, brain_queue, APP_CONFIG['slack_channel_id']))
            tg.create_task(brain_worker(brain_queue, sender_queues, persona_manager, state_manager, db))
            tg.create_task(scheduler_worker(sender_queues, persona_manager, state_manager, db))
            tg.create_task(telegram_sender_worker(sender_queues["telegram_sender_queue"], sender_clients))
            tg.create_task(slack_sender_worker(sender_queues["slack_sender_queue"], slack_web_client))
        
            print("--- Bot is fully operational on Telegram and Slack. Press Ctrl+C to stop. ---")
            # The 'with' block will not exit until all tasks are complete or one fails.

    except* Exception as eg:
        # This syntax is specific to TaskGroup and handles multiple exceptions
        print(f"--- Main task group encountered errors: ---")
        for exc in eg.exceptions:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
    finally:
        # When the 'with' block exits (due to error or cancellation), the TaskGroup
        # ensures all tasks are stopped. We just need to disconnect clients.
        print("[MAIN] Shutting down...")
        for client in all_clients:
            if client.is_connected():
                await client.disconnect()
        print("[MAIN] All clients disconnected. Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n[MAIN] Shutdown requested by user.")