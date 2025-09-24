# File: src/listeners/telegram_listener.py

import asyncio
import logging
from telethon import TelegramClient, events
from asyncio import Queue, AbstractEventLoop
from telethon.sessions import StringSession

from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

logger = logging.getLogger(__name__)

def run_telethon_in_thread(
    client: TelegramClient, 
    bot_instance: BotInstance, 
    brain_queue: Queue, 
    main_loop: AbstractEventLoop
):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    user_id = bot_instance.user_id
    
    # Configure Telethon's own logger to be less noisy
    logging.getLogger('telethon').setLevel(logging.WARNING)
    
    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event):
        message = event.message
        target_group_id_str = str(bot_instance.credentials.get("telegram", {}).get("telegram_group_id"))
        
        if not message or not message.text or str(message.chat_id) != target_group_id_str:
            return
            
        logger.info(f"Received Telegram message for user {user_id}: '{message.text[:50]}...'")
        
        internal_msg = InternalMessage(
            platform='telegram', channel_id=str(message.chat_id),
            message_id=str(message.id), text=message.text,
            sender_id=str(getattr(message, 'sender_id', 'unknown'))
        )
        logger.debug(f"Putting message for {user_id} onto brain queue ID: {id(brain_queue)}")
        main_loop.call_soon_threadsafe(brain_queue.put_nowait, internal_msg)

    logger.info(f"Telethon thread: Connecting client for user {user_id}...")
    with client:
        logger.info(f"Telethon thread: Client connected for {user_id}. Listening for messages...")
        client.run_until_disconnected()
    logger.info(f"Telethon thread: Client disconnected for {user_id}.")

async def telegram_listener_task(brain_queue: Queue, bot_instance: BotInstance):
    user_id = bot_instance.user_id
    logger.info(f"Main Telegram listener task starting for {user_id}.")
    
    client = None
    try:
        tg_config = bot_instance.credentials.get("telegram", {})
        ingestor_config = tg_config.get("ingestor_config", {})
        api_id, api_hash, session_string = (
            ingestor_config.get("api_id"), ingestor_config.get("api_hash"),
            ingestor_config.get("session_string")
        )
        
        if not all([api_id, api_hash, session_string]):
            logger.critical(f"FATAL: Missing Telegram ingestor credentials for {user_id}. Task exiting.")
            return

        main_event_loop = asyncio.get_running_loop()
        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        
        logger.info(f"Offloading Telethon client for {user_id} to a dedicated thread...")
        await asyncio.to_thread(
            run_telethon_in_thread,
            client,
            bot_instance,
            brain_queue,
            main_event_loop
        )

    except asyncio.CancelledError:
        logger.info(f"Main Telegram listener task for {user_id} cancelled.")
    except Exception:
        logger.critical(f"CRITICAL ERROR in main Telegram listener task for {user_id}", exc_info=True)
    finally:
        if client and client.is_connected():
            logger.info(f"Disconnecting Telethon client from main task for user {user_id}...")
            await client.disconnect()
        logger.info(f"Main Telegram listener task for {user_id} has finished.")