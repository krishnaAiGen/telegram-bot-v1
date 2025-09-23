# File: src/orchestrator.py

import asyncio
import logging
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
from src.config.settings import load_server_config

# Get a logger instance for this module
logger = logging.getLogger(__name__)

# --- Global State for Orchestrator Management ---
RUNNING_BOTS: Dict[str, Dict[str, Any]] = {}
STARTING_BOTS: Dict[str, bool] = {}
db = None
fernet = None
shutdown_event = asyncio.Event()
orchestrator_task = None # This will hold the main running task

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
                try:
                    decrypted_data[new_key] = fernet_instance.decrypt(value.encode()).decode()
                except Exception:
                    logger.warning(f"Could not decrypt key '{key}'. It may be invalid or corrupted.")
            else:
                decrypted_data[key] = value
        else:
            decrypted_data[key] = value
    return decrypted_data

async def start_bot_instance(user_id: str, user_data: dict):
    if user_id in RUNNING_BOTS or STARTING_BOTS.get(user_id):
        logger.debug(f"Start command for user {user_id} ignored: already running or starting.")
        return
        
    STARTING_BOTS[user_id] = True
    logger.info(f"Starting instance for user: {user_id}")
    
    persona_config = user_data.get("personaConfig", {})
    if not persona_config.get("liveTeam"):
        logger.warning(f"Aborting start for {user_id}: liveTeam is empty.")
        STARTING_BOTS.pop(user_id, None)
        return
        
    connections = {}
    connections_ref = db.collection("customers").document(user_id).collection("connections")
    for doc in connections_ref.stream():
        connections[doc.id] = doc.to_dict()
    
    user_config = {"personaConfig": persona_config, "connections": decrypt_credentials(connections, fernet)}
    
    instance = BotInstance(user_id=user_id, user_config=user_config)
    
    logger.debug(f"Initializing BotInstance for {user_id} (includes embedding generation)...")
    await instance.initialize(db=db)
    logger.debug(f"BotInstance for {user_id} initialized successfully.")
    
    brain_queue = asyncio.Queue()
    logger.debug(f"Brain Queue created for {user_id} with ID: {id(brain_queue)}")
    
    sender_queues = {
        "telegram_sender_queue": asyncio.Queue(),
        "slack_sender_queue": asyncio.Queue(),
        "discord_sender_queue": asyncio.Queue()
    }
    
    tasks = [
        asyncio.create_task(brain_worker(brain_queue, sender_queues, instance, db)),
        asyncio.create_task(scheduler_worker(sender_queues, instance, db))
    ]
    
    active_platforms = persona_config.get("activePlatforms", [])
    logger.info(f"Activating platforms for {user_id}: {active_platforms}")
    
    if "telegram" in active_platforms:
        logger.debug(f"Creating Telegram tasks for {user_id}")
        tasks.append(asyncio.create_task(telegram_listener_task(brain_queue, instance)))
        tasks.append(asyncio.create_task(telegram_sender_task(sender_queues['telegram_sender_queue'], instance)))

    if "slack" in active_platforms:
        logger.debug(f"Creating Slack tasks for {user_id}")
        tasks.append(asyncio.create_task(slack_listener_task(brain_queue, instance)))
        tasks.append(asyncio.create_task(slack_sender_task(sender_queues['slack_sender_queue'], instance)))

    if "discord" in active_platforms:
        logger.debug(f"Creating Discord tasks for {user_id}")
        discord_command_queue = asyncio.Queue()
        tasks.append(asyncio.create_task(discord_listener_task(brain_queue, instance, discord_command_queue)))
        tasks.append(asyncio.create_task(discord_sender_task(sender_queues['discord_sender_queue'], instance, discord_command_queue)))
    
    RUNNING_BOTS[user_id] = {"instance": instance, "tasks": tasks}
    STARTING_BOTS.pop(user_id, None)
    logger.info(f"Instance for user {user_id} is now running with {len(tasks)} tasks.")

async def stop_bot_instance(user_id: str):
    if user_id not in RUNNING_BOTS:
        logger.debug(f"Stop command for user {user_id} ignored: not currently running.")
        return
        
    logger.info(f"Stopping instance for user: {user_id}")
    bot_info = RUNNING_BOTS.pop(user_id)
    for task in bot_info.get("tasks", []):
        task.cancel()
    
    await asyncio.gather(*bot_info.get("tasks", []), return_exceptions=True)
    logger.info(f"Instance for user {user_id} stopped.")

async def command_worker(queue: asyncio.Queue):
    logger.info("Command worker started.")
    while True:
        try:
            command, user_id, user_data = await queue.get()
            logger.debug(f"Command worker received command: '{command}' for user: {user_id}")
            if command == "START":
                await start_bot_instance(user_id, user_data)
            elif command == "STOP":
                await stop_bot_instance(user_id)
            queue.task_done()
        except asyncio.CancelledError:
            logger.info("Command worker is shutting down.")
            break
        except Exception:
            logger.critical("CRITICAL ERROR in command_worker", exc_info=True)

def on_snapshot_factory(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    def on_snapshot(col_snapshot, changes, read_time):
        logger.debug("--- Firestore snapshot received! Processing changes... ---")
        for change in changes:
            user_id = change.document.id
            change_type = change.type.name
            logger.debug(f"  -> User: {user_id}, Change Type: {change_type}")

            if change_type == 'REMOVED':
                if user_id in RUNNING_BOTS:
                    logger.info(f"User document {user_id} removed. Sending STOP signal.")
                    loop.call_soon_threadsafe(queue.put_nowait, ("STOP", user_id, None))
                continue

            if change_type in ['ADDED', 'MODIFIED']:
                user_data = change.document.to_dict()
                persona_config = user_data.get("personaConfig", {})
                is_active_desired = persona_config.get("isActive", False)
                is_currently_running = user_id in RUNNING_BOTS or STARTING_BOTS.get(user_id)
                
                logger.debug(f"  -> User: {user_id} | Desired: {is_active_desired} | Current: {is_currently_running}")

                if is_active_desired and not is_currently_running:
                    logger.info(f"  -> Action for {user_id}: Sending START signal.")
                    loop.call_soon_threadsafe(queue.put_nowait, ("START", user_id, user_data))
                elif not is_active_desired and is_currently_running:
                    logger.info(f"  -> Action for {user_id}: Sending STOP signal.")
                    loop.call_soon_threadsafe(queue.put_nowait, ("STOP", user_id, None))
                else:
                    logger.debug(f"  -> Action for {user_id}: No state change needed.")
        logger.debug("--- Finished processing Firestore snapshot. ---")
    return on_snapshot

async def run_orchestrator():
    global db, fernet
    
    try:
        server_config = load_server_config()
    except (ValueError, FileNotFoundError) as e:
        logger.critical(f"Orchestrator cannot start: CRITICAL CONFIGURATION ERROR: {e}", exc_info=True)
        return

    if not firebase_admin._apps:
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

    logger.info("Orchestrator's real-time listener is now active.")
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        logger.info("Orchestrator shutdown signal received.")
    finally:
        logger.info("Cleaning up orchestrator...")
        query_watch.unsubscribe()
        command_task.cancel()
        await command_task # Wait for it to finish
        running_user_ids = list(RUNNING_BOTS.keys())
        if running_user_ids:
            logger.info(f"Stopping {len(running_user_ids)} running bot instance(s)...")
            await asyncio.gather(*(stop_bot_instance(user_id) for user_id in running_user_ids))
        
        await asyncio.sleep(1.0) 
        logger.info("All instances stopped. Orchestrator exited gracefully.")

# --- NEW CONTROLLER FUNCTIONS for Lifespan Manager ---

def start_orchestrator_task():
    """Creates and starts the main orchestrator task in the background."""
    global orchestrator_task
    if orchestrator_task and not orchestrator_task.done():
        logger.warning("Start command received, but orchestrator task is already running.")
        return
    logger.info("Starting orchestrator as a background task...")
    orchestrator_task = asyncio.create_task(run_orchestrator())

async def stop_orchestrator_task():
    """Signals the orchestrator to shut down and waits for it to complete."""
    global orchestrator_task
    if not orchestrator_task or orchestrator_task.done():
        logger.warning("Stop command received, but orchestrator is not running.")
        return
    
    logger.info("Signaling orchestrator to shut down...")
    shutdown_event.set()
    
    try:
        await asyncio.wait_for(orchestrator_task, timeout=15.0)
    except asyncio.TimeoutError:
        logger.error("Orchestrator did not shut down gracefully within 15 seconds.")
    except asyncio.CancelledError:
        pass # This can happen during forced shutdown and is okay.
        
    logger.info("Orchestrator shutdown process complete.")