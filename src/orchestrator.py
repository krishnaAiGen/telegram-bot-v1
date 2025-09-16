# src/orchestrator.py

import asyncio
from typing import Dict, Any
import firebase_admin
from firebase_admin import credentials, firestore
from cryptography.fernet import Fernet

# Import all your components
from src.bot_instance import BotInstance
from src.workers.brain import brain_worker
from src.workers.scheduler import scheduler_worker
from src.listeners.telegram_listener import telegram_listener_task
from src.senders.telegram_sender import telegram_sender_task
from src.listeners.slack_listener import slack_listener_task
from src.senders.slack_sender import slack_sender_task
from src.listeners.discord_listener import discord_listener_task
from src.senders.discord_sender import discord_sender_task

# --- Global State Management ---
RUNNING_BOTS: Dict[str, Dict[str, Any]] = {}
STARTING_BOTS: Dict[str, bool] = {}
db = None
fernet = None
shutdown_event = asyncio.Event()


def decrypt_credentials(encrypted_data: dict, fernet_instance: Fernet) -> dict:
    decrypted_data = {}
    for key, value in encrypted_data.items():
        if isinstance(value, dict):
            decrypted_data[key] = decrypt_credentials(value, fernet_instance)
        elif isinstance(value, str):
            new_key = None
            if '_encrypted' in key: new_key = key.replace('_encrypted', '')
            elif key == 'encrypted_key': new_key = 'api_key'
            if new_key:
                try: decrypted_data[new_key] = fernet_instance.decrypt(value.encode()).decode()
                except Exception as e: print(f"Warning: Could not decrypt key '{key}'. Error: {e}")
            else: decrypted_data[key] = value
        else: decrypted_data[key] = value
    return decrypted_data


async def start_bot_instance(user_id: str, user_data: dict):
    if user_id in RUNNING_BOTS or STARTING_BOTS.get(user_id): return
    STARTING_BOTS[user_id] = True
    
    print(f"[ORCHESTRATOR] Starting instance for user: {user_id}")
    
    persona_config = user_data.get("personaConfig", {})
    if not persona_config.get("liveTeam"):
        print(f"[ORCHESTRATOR] Aborting start for {user_id}: liveTeam is empty.")
        STARTING_BOTS.pop(user_id, None); return
        
    connections = {}
    connections_ref = db.collection("customers").document(user_id).collection("connections")
    for doc in connections_ref.stream():
        connections[doc.id] = doc.to_dict()
    
    user_config = {"personaConfig": persona_config, "connections": decrypt_credentials(connections, fernet)}
    
    # Step 1: Create the instance object
    instance = BotInstance(user_id=user_id, user_config=user_config)

    # --- THIS IS THE FIX ---
    # Step 2: FULLY initialize the instance, including the slow embedding generation, BEFORE doing anything else.
    print("\n--- [ORCH-DEBUG] Initializing instance (embeddings call)... ---\n")
    await instance.initialize(db=db)
    # By the time this 'await' completes, the instance is 100% ready.
    # --- END OF FIX ---

    print("\n--- [ORCH-DEBUG] CREATING QUEUES AND TASKS ---")
    brain_queue = asyncio.Queue()
    print(f"--- [ORCH-DEBUG] Brain Queue created with ID: {id(brain_queue)} ---")
    
    sender_queues = {
        "telegram_sender_queue": asyncio.Queue(),
        "slack_sender_queue": asyncio.Queue(),
        "discord_sender_queue": asyncio.Queue()
    }
    
    # Step 3: Now that the instance is ready, create all the tasks that will use it.
    tasks = [
        asyncio.create_task(brain_worker(brain_queue, sender_queues, instance, db)),
        asyncio.create_task(scheduler_worker(sender_queues, instance, db))
    ]
    
    active_platforms = persona_config.get("activePlatforms", [])
    
    if "telegram" in active_platforms:
        print(f" -> [ORCH-DEBUG] Creating Telegram tasks, passing Brain Queue ID: {id(brain_queue)}")
        tasks.append(asyncio.create_task(telegram_listener_task(brain_queue, instance)))
        tasks.append(asyncio.create_task(telegram_sender_task(sender_queues['telegram_sender_queue'], instance)))

    if "slack" in active_platforms:
        print(f" -> [ORCH-DEBUG] Creating Slack tasks, passing Brain Queue ID: {id(brain_queue)}")
        tasks.append(asyncio.create_task(slack_listener_task(brain_queue, instance)))
        tasks.append(asyncio.create_task(slack_sender_task(sender_queues['slack_sender_queue'], instance)))

    if "discord" in active_platforms:
        print(f" -> [ORCH-DEBUG] Creating Discord tasks, passing Brain Queue ID: {id(brain_queue)}")
        
        # --- THIS IS THE FIX ---
        # No more complex shared events or lists. Just a simple command queue.
        discord_command_queue = asyncio.Queue()
        
        tasks.append(asyncio.create_task(
            discord_listener_task(brain_queue, instance, discord_command_queue)
        ))
        tasks.append(asyncio.create_task(
            discord_sender_task(sender_queues['discord_sender_queue'], instance, discord_command_queue)
        ))
    # The line `await instance.initialize(db=db)` has been moved from here to up above.
    
    RUNNING_BOTS[user_id] = {"instance": instance, "tasks": tasks}
    print(f"[ORCHESTRATOR] Instance for user {user_id} is now running with {len(tasks)} tasks.")
    STARTING_BOTS.pop(user_id, None)

async def stop_bot_instance(user_id: str):
    if user_id not in RUNNING_BOTS: return
    print(f"[ORCHESTRATOR] Stopping instance for user: {user_id}")
    bot_info = RUNNING_BOTS.pop(user_id)
    for task in bot_info.get("tasks", []): task.cancel()
    await asyncio.gather(*bot_info.get("tasks", []), return_exceptions=True)
    print(f"[ORCHESTRATOR] Instance for user {user_id} stopped.")


async def command_worker(queue: asyncio.Queue):
    while True:
        try:
            command, user_id, user_data = await queue.get()
            if command == "START": await start_bot_instance(user_id, user_data)
            elif command == "STOP": await stop_bot_instance(user_id)
            queue.task_done()
        except asyncio.CancelledError: break
        except Exception as e: print(f"CRITICAL ERROR in command_worker: {e}")


def on_snapshot_factory(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            user_id = change.document.id
            if change.type.name == 'REMOVED':
                if user_id in RUNNING_BOTS: loop.call_soon_threadsafe(queue.put_nowait, ("STOP", user_id, None))
                continue
            if change.type.name in ['ADDED', 'MODIFIED']:
                user_data = change.document.to_dict()
                is_active_desired = user_data.get("personaConfig", {}).get("isActive", False)
                is_currently_running = user_id in RUNNING_BOTS or STARTING_BOTS.get(user_id)
                if is_active_desired and not is_currently_running:
                    loop.call_soon_threadsafe(queue.put_nowait, ("START", user_id, user_data))
                elif not is_active_desired and is_currently_running:
                    loop.call_soon_threadsafe(queue.put_nowait, ("STOP", user_id, None))
    return on_snapshot


async def run_orchestrator(server_config: dict):
    global db, fernet
    cred = credentials.Certificate(server_config["firebase_cred_path"])
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    fernet = Fernet(server_config["secret_key"].encode())
    
    command_queue = asyncio.Queue()
    main_loop = asyncio.get_running_loop()
    command_task = asyncio.create_task(command_worker(command_queue))
    
    snapshot_callback = on_snapshot_factory(command_queue, main_loop)
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
        command_task.cancel()
        running_user_ids = list(RUNNING_BOTS.keys())
        if running_user_ids:
            await asyncio.gather(*(stop_bot_instance(user_id) for user_id in running_user_ids))
        
        # --- THIS IS THE FIX ---
        # Give background tasks a very short moment to finish closing.
        # This prevents the 'Event loop is closed' error from aiohttp.
        await asyncio.sleep(1.0) 
        # --- END OF FIX ---

        print("[ORCHESTRATOR] All instances stopped. Exiting.")