# src/senders/slack_sender.py

import asyncio
import random
from slack_sdk.web.async_client import AsyncWebClient
from config.settings import APP_CONFIG

async def slack_sender_worker(
    queue: asyncio.Queue,
    slack_client: AsyncWebClient
):
    """
    A dedicated worker that listens on a queue and sends messages to Slack.
    """
    print("[SLACK_SENDER] Worker started.")
    while True:
        try:
            msg = await queue.get()
            
            channel_id = msg.get("channel_id")
            text = msg.get("message")

            if not all([channel_id, text]):
                print(f"[SLACK_SENDER] Skipping invalid message payload: {msg}")
                queue.task_done()
                continue

            await slack_client.chat_postMessage(
                channel=channel_id,
                text=text
            )
            print(f"[SLACK_SENDER] Message sent successfully to channel {channel_id}.")

            # Optional: Add a small delay if you want to rate-limit Slack messages too
            delay = random.uniform(APP_CONFIG['min_send_delay_secs'], APP_CONFIG['max_send_delay_secs'])
            await asyncio.sleep(delay)
            queue.task_done()

        except Exception as e:
            print(f"CRITICAL ERROR in Slack Sender Worker: {e}")
            await asyncio.sleep(10)