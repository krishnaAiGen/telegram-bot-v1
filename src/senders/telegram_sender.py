# File: src/senders/telegram_sender.py

import asyncio
import logging
import random
from telethon import TelegramClient
from asyncio import Queue
from telethon.sessions import StringSession

from src.bot_instance import BotInstance

logger = logging.getLogger(__name__)

async def telegram_sender_task(queue: Queue, bot_instance: BotInstance):
    user_id = bot_instance.user_id
    logger.info(f"Telegram sender task starting for user: {user_id}")
    
    tg_config = bot_instance.credentials.get("telegram", {})
    senders_config = tg_config.get("senders_config", {})
    logger.debug(f"Loaded senders config for {user_id}: {senders_config}")

    if not senders_config:
        logger.critical(f"FATAL: No senders_config defined for user {user_id}. Exiting task.")
        return

    sender_clients: dict[str, TelegramClient] = {}
    
    for name, config in senders_config.items():
        logger.debug(f"Processing sender '{name}' for user {user_id}")
        api_id = config.get("api_id")
        api_hash = config.get("api_hash")
        session_string = config.get("session_string")
        if all([api_id, api_hash, session_string]):
            session = StringSession(session_string)
            sender_clients[name] = TelegramClient(session, int(api_id), api_hash)
            logger.debug(f"Client object created for sender '{name}'.")
        else:
            logger.warning(f"Missing full credentials for sender '{name}'. It will be skipped.")

    if not sender_clients:
        logger.critical(f"No valid Telegram sender clients could be created for user {user_id}. Exiting task.")
        return

    try:
        logger.info(f"Connecting {len(sender_clients)} Telegram sender client(s) for user {user_id}...")
        for name, client in list(sender_clients.items()):
            try:
                logger.debug(f"Attempting to start client '{name}'...")
                await asyncio.wait_for(client.start(), timeout=30.0) 
                logger.info(f"Client '{name}' connected successfully.")
            except Exception:
                logger.error(f"CRITICAL STARTUP ERROR for client '{name}'", exc_info=True)
                del sender_clients[name]
        
        if not sender_clients:
            logger.critical(f"All Telegram sender clients failed to connect for user {user_id}. Exiting task.")
            return

        logger.info(f"Finished connecting Telegram senders for user {user_id}. {len(sender_clients)} client(s) are active.")

        while True:
            msg = await queue.get()
            logger.debug(f"Telegram sender for {user_id} received payload from brain: {msg}")

            try:
                channel_id = msg.get("channel_id")
                text = msg.get("message")
                
                if not all([channel_id, text]):
                    logger.warning(f"Skipping invalid payload (missing channel or text): {msg}")
                    continue
                
                telegram_user_name = msg.get("telegram_user")
                client_to_use = sender_clients.get(telegram_user_name)

                if not client_to_use and sender_clients:
                    fallback_name = list(sender_clients.keys())[0]
                    client_to_use = sender_clients[fallback_name]
                    logger.warning(f"Client for '{telegram_user_name}' not found. Falling back to first available: '{fallback_name}'.")
                
                if client_to_use and client_to_use.is_connected():
                    me = await client_to_use.get_me()
                    sender_name = me.username or me.first_name
                    await client_to_use.send_message(int(channel_id), text)
                    logger.info(f"Message sent to Telegram for user {user_id} via {sender_name}.")
                else:
                    logger.error(f"Could not find a valid, connected client to send message for user {user_id}.")

                min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 5.0)
                max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 15.0)
                delay = random.uniform(min_delay, max_delay)
                logger.debug(f"Telegram sender for {user_id} delaying for {delay:.2f} seconds.")
                await asyncio.sleep(delay)

            except Exception:
                logger.error(f"CRITICAL SEND ERROR in Telegram Sender for user {user_id}", exc_info=True)
            
            finally:
                queue.task_done()

    except asyncio.CancelledError:
        logger.info(f"Telegram sender task for user {user_id} cancelled.")
    except Exception:
        logger.critical(f"FATAL ERROR in Telegram Sender main task for user {user_id}", exc_info=True)
    finally:
        logger.info(f"Disconnecting Telegram sender clients for user {user_id}...")
        await asyncio.gather(*(c.disconnect() for c in sender_clients.values() if c.is_connected()), return_exceptions=True)
        logger.info(f"Telegram sender clients for user {user_id} disconnected.")