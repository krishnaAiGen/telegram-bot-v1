import asyncio
import random
from telethon import TelegramClient
from config.settings import APP_CONFIG




async def sender_worker(sender_queue: asyncio.Queue, sender_clients: dict[str, TelegramClient]):
    print("[SENDER] Worker started. Waiting for messages to send...")
    while True:
        try:
            msg = await sender_queue.get()
            user, text = msg.get("telegram_user"), msg.get("message")

            if not text or not user:
                sender_queue.task_done()
                continue
            
            client_to_use = sender_clients.get(user)
            if not client_to_use or not client_to_use.is_connected():
                sender_queue.task_done()
                continue

            await client_to_use.send_message(APP_CONFIG['telegram_group_id'], text)
            print(f"[SENDER] Message sent successfully via {user}.")
            
            delay = random.uniform(APP_CONFIG['min_send_delay_secs'], APP_CONFIG['max_send_delay_secs'])
            await asyncio.sleep(delay)
            sender_queue.task_done()
        except Exception as e:
            print(f"CRITICAL ERROR in Sender Worker: {e}")
            await asyncio.sleep(10)
