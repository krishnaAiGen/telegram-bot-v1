# src/senders/slack_sender.py

import asyncio
import random
from slack_sdk.web.async_client import AsyncWebClient
from asyncio import Queue

from src.bot_instance import BotInstance

async def slack_sender_task(queue: Queue, bot_instance: BotInstance):
    """A self-contained task that sends messages to Slack."""
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("slack", {})
    bot_token = creds.get("bot_token")

    if not bot_token:
        print(f"[SLACK SENDER] Cannot start for user {user_id}: missing bot token.")
        return

    client = AsyncWebClient(token=bot_token)
    print(f"[SLACK SENDER] Worker started for user: {user_id}")

    while True:
        try:
            msg = await queue.get()
            channel_id = msg.get("channel_id")
            text = msg.get("message")

            if not all([channel_id, text]):
                queue.task_done()
                continue

            await client.chat_postMessage(channel=channel_id, text=text)
            print(f"[SLACK SENDER] Message sent for user {user_id}.")
            
            # Use delays from instance-specific settings
            min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 1.0)
            max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 3.0)
            await asyncio.sleep(random.uniform(min_delay, max_delay))

            queue.task_done()
        except asyncio.CancelledError:
            print(f"[SLACK SENDER] Task cancelled for user {user_id}.")
            break
        except Exception as e:
            print(f"CRITICAL ERROR in Slack Sender for user {user_id}: {e}")
            await asyncio.sleep(5)