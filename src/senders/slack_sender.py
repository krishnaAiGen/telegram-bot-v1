# File: src/senders/slack_sender.py

import asyncio
import logging
import random
from slack_sdk.web.async_client import AsyncWebClient
from asyncio import Queue

from src.bot_instance import BotInstance

logger = logging.getLogger(__name__)

async def slack_sender_task(queue: Queue, bot_instance: BotInstance):
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("slack", {})
    bot_token = creds.get("bot_token")

    if not bot_token:
        logger.critical(f"Cannot start Slack sender for user {user_id}: missing bot token.")
        return

    client = AsyncWebClient(token=bot_token)
    logger.info(f"Slack sender worker started for user: {user_id}")

    while True:
        try:
            msg = await queue.get()
            logger.debug(f"Slack sender for {user_id} received payload from brain: {msg}")

            channel_id = msg.get("channel_id")
            text = msg.get("message")

            if not all([channel_id, text]):
                logger.warning(f"Slack sender for {user_id} skipping invalid payload: {msg}")
                queue.task_done()
                continue

            await client.chat_postMessage(channel=channel_id, text=text)
            logger.info(f"Message sent to Slack for user {user_id}.")
            
            min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 1.0)
            max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 3.0)
            delay = random.uniform(min_delay, max_delay)
            logger.debug(f"Slack sender for {user_id} delaying for {delay:.2f} seconds.")
            await asyncio.sleep(delay)

            queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"Slack sender task cancelled for user {user_id}.")
            break
        except Exception:
            logger.critical(f"CRITICAL ERROR in Slack Sender for user {user_id}", exc_info=True)
            await asyncio.sleep(5)