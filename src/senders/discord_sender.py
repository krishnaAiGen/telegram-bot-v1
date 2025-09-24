# File: src/senders/discord_sender.py

import asyncio
import logging
from asyncio import Queue
from src.bot_instance import BotInstance

logger = logging.getLogger(__name__)

async def discord_sender_task(
    sender_queue: Queue,
    bot_instance: BotInstance,
    command_queue: Queue
):
    user_id = bot_instance.user_id
    logger.info(f"Discord sender bridge worker starting for user {user_id}.")
    
    while True:
        try:
            payload = await sender_queue.get()
            logger.debug(f"Discord sender for {user_id} received payload from brain: {payload}")
            
            await command_queue.put(payload)
            
            logger.debug(f"Relayed message for user {user_id} to listener's internal command queue.")
            
            sender_queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"Discord sender bridge worker for user {user_id} cancelled.")
            break
        except Exception:
            logger.critical(f"CRITICAL ERROR in Discord Sender Bridge for user {user_id}", exc_info=True)
            await asyncio.sleep(5)