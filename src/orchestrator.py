# src/orchestrator.py
import asyncio
import threading
from typing import Dict, Any

import firebase_admin
from firebase_admin import credentials, firestore
from cryptography.fernet import Fernet

from src.bot_instance import BotInstance
from src.workers.brain import brain_worker
from src.workers.scheduler import scheduler_worker
from src.listeners.telegram_listener import telegram_listener_task
from src.senders.telegram_sender import telegram_sender_task
from src.listeners.slack_listener import slack_listener_task
from src.senders.slack_sender import slack_sender_task
from src.listeners.discord_listener import discord_listener_task
from src.senders.discord_sender import discord_sender_task

# Global state
RUNNING_BOTS: Dict[str, Dict[str, Any]] = {}
db = None
fernet = None
shutdown_event = asyncio.Event()


# In src/orchestrator.py

# In src/orchestrator.py

def decrypt_credentials(encrypted_creds: dict, fernet_instance: Fernet) -> dict:
    """
    Helper function to recursively decrypt all credentials for a user.
    This version uses a more general rule for finding encrypted keys.
    """
    decrypted = {}
    for platform, cred_dict in encrypted_creds.items():
        decrypted_platform_creds = {}
        for key, value in cred_dict.items():
            # --- THIS IS THE FINAL, CORRECT LOGIC ---
            # If 'encrypted' is part of the key name, decrypt it.
            if isinstance(value, str) and 'encrypted' in key:
                # The new key will be the original name without 'encrypted' or '_encrypted'.
                new_key = key.replace('_encrypted', '').replace('encrypted_', '')
                try:
                    decrypted_platform_creds[new_key] = fernet_instance.decrypt(value.encode()).decode()
                except Exception as e:
                    print(f"Warning: Could not decrypt '{key}' for {platform}. Error: {e}")
            else:
                 # If not an encrypted key, just copy it over.
                 decrypted_platform_creds[key] = value
            # --- END OF FIX ---
        decrypted[platform] = decrypted_platform_creds
    return decrypted

async def start_bot_instance(user_id: str, user_data: dict):
    """Creates and starts all async tasks for a single user's bot."""
    if user_id in RUNNING_BOTS:
        return

    # --- THIS IS THE CRITICAL PRE-FLIGHT CHECK ---
    persona_config = user_data.get("personaConfig", {})
    if not persona_config.get("liveTeam"):
        print(f"[ORCHESTRATOR] Aborting start for {user_id}: liveTeam is empty.")
        return
    # --- END OF CHECK ---

    print(f"[ORCHESTRATOR] Starting instance for user: {user_id}")

    connections = {}
    connections_ref = db.collection("customers").document(user_id).collection("connections")
    for doc in connections_ref.stream():
        connections[doc.id] = doc.to_dict()
    
    # --- DEBUG STEP 1: Print the raw config BEFORE decryption
    print(f"\n--- DEBUG: Raw Config Before Decryption ---")
    print(f"  -> Raw Connections: {connections}")
    # --- END OF CHECK ---

    print(f"[ORCHESTRATOR] Starting instance for user: {user_id}")

    connections = {}
    connections_ref = db.collection("customers").document(user_id).collection("connections")
    for doc in connections_ref.stream():
        connections[doc.id] = doc.to_dict()

    user_config = {
        "personaConfig": persona_config,
        "connections": connections
    }
    
    user_config['connections'] = decrypt_credentials(user_config.get('connections', {}), fernet)
    
    print(f"\n--- DEBUG: Final user_config for BotInstance ---")
    print(f"  -> {user_config}\n")
    instance = BotInstance(user_id=user_id, user_config=user_config)
    await instance.initialize(db=db)

    brain_queue = asyncio.Queue()
    sender_queues = {
        "telegram_sender_queue": asyncio.Queue(),
        "slack_sender_queue": asyncio.Queue(),
        "discord_sender_queue": asyncio.Queue(),
    }
    
    tasks = [
        asyncio.create_task(brain_worker(brain_queue, sender_queues, instance, db)),
        asyncio.create_task(scheduler_worker(sender_queues, instance, db))
    ]

    active_platforms = persona_config.get("activePlatforms", [])
    
    if "telegram" in active_platforms:
        tasks.append(asyncio.create_task(telegram_listener_task(brain_queue, instance)))
        tasks.append(asyncio.create_task(telegram_sender_task(sender_queues['telegram_sender_queue'], instance)))
    if "slack" in active_platforms:
        tasks.append(asyncio.create_task(slack_listener_task(brain_queue, instance)))
        tasks.append(asyncio.create_task(slack_sender_task(sender_queues['slack_sender_queue'], instance)))
    if "discord" in active_platforms:
        shared_client_setup_event = asyncio.Event()
        shared_client_object = []
        tasks.append(asyncio.create_task(discord_listener_task(brain_queue, instance, shared_client_setup_event, shared_client_object)))
        tasks.append(asyncio.create_task(discord_sender_task(sender_queues['discord_sender_queue'], instance, shared_client_setup_event, shared_client_object)))
    
    RUNNING_BOTS[user_id] = {"instance": instance, "tasks": tasks}
    print(f"[ORCHESTRATOR] Instance for user {user_id} is now running with {len(tasks)} tasks.")

async def stop_bot_instance(user_id: str):
    if user_id not in RUNNING_BOTS: return
    print(f"[ORCHESTRATOR] Stopping instance for user: {user_id}")
    bot_info = RUNNING_BOTS.pop(user_id)
    tasks_to_stop = bot_info.get("tasks", [])
    for task in tasks_to_stop:
        task.cancel()
    await asyncio.gather(*tasks_to_stop, return_exceptions=True)
    print(f"[ORCHESTRATOR] Instance for user {user_id} stopped.")

def on_snapshot_factory(loop: asyncio.AbstractEventLoop):
    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            user_id = change.document.id
            if change.type.name in ['ADDED', 'MODIFIED']:
                user_data = change.document.to_dict()
                is_active_desired = user_data.get("personaConfig", {}).get("isActive", False)
                is_currently_running = user_id in RUNNING_BOTS
                if is_active_desired and not is_currently_running:
                    loop.call_soon_threadsafe(asyncio.create_task, start_bot_instance(user_id, user_data))
                elif not is_active_desired and is_currently_running:
                    loop.call_soon_threadsafe(asyncio.create_task, stop_bot_instance(user_id))
                elif is_active_desired and is_currently_running:
                    loop.call_soon_threadsafe(asyncio.create_task, stop_bot_instance(user_id))
                    loop.call_soon_threadsafe(asyncio.create_task, start_bot_instance(user_id, user_data))
            elif change.type.name == 'REMOVED':
                if user_id in RUNNING_BOTS:
                    loop.call_soon_threadsafe(asyncio.create_task, stop_bot_instance(user_id))
    return on_snapshot

async def run_orchestrator(server_config: dict):
    global db, fernet
    cred = credentials.Certificate(server_config["firebase_cred_path"])
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    fernet = Fernet(server_config["secret_key"].encode())
    
    main_loop = asyncio.get_running_loop()
    snapshot_callback = on_snapshot_factory(main_loop)
    col_query = db.collection('customers')
    query_watch = col_query.on_snapshot(snapshot_callback)

    print("[ORCHESTRATOR] Real-time listener is now active...")
    try:
        await shutdown_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("[ORCHESTRATOR] Shutdown signal received.")
    finally:
        print("[ORCHESTRATOR] Cleaning up...")
        query_watch.unsubscribe()
        running_user_ids = list(RUNNING_BOTS.keys())
        if running_user_ids:
            await asyncio.gather(*(stop_bot_instance(user_id) for user_id in running_user_ids))
        print("[ORCHESTRATOR] All instances stopped. Exiting.")