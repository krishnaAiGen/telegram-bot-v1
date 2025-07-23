# src/senders/telegram_sender.py

import asyncio
import random
from telethon import TelegramClient
from config.settings import APP_CONFIG

async def telegram_sender_worker(
    queue: asyncio.Queue,
    sender_clients: dict[str, TelegramClient]
):
    """
    A dedicated worker that listens on a queue and sends messages to Telegram.
    """
    print("[TELEGRAM_SENDER] Worker started.")
    while True:
        try:
            msg = await queue.get()
            
            channel_id = msg.get("channel_id")
            text = msg.get("message")
            telegram_user = msg.get("telegram_user") # The specific bot account to use

            if not all([channel_id, text, telegram_user]):
                print(f"[TELEGRAM_SENDER] Skipping invalid message payload: {msg}")
                queue.task_done()
                continue
            
            client_to_use = sender_clients.get(telegram_user)
            if client_to_use and client_to_use.is_connected():
                # channel_id from our InternalMessage is a string, needs to be int for Telethon
                await client_to_use.send_message(int(channel_id), text)
                print(f"[TELEGRAM_SENDER] Message sent successfully via {telegram_user}.")
            else:
                print(f"[TELEGRAM_SENDER] Client for user '{telegram_user}' not found or disconnected.")

            delay = random.uniform(APP_CONFIG['min_send_delay_secs'], APP_CONFIG['max_send_delay_secs'])
            await asyncio.sleep(delay)
            queue.task_done()
            
        except Exception as e:
            print(f"CRITICAL ERROR in Telegram Sender Worker: {e}")
            await asyncio.sleep(10) # Avoid rapid-fire errors