# src/senders/telegram_sender.py

import asyncio
import random
import os
from telethon import TelegramClient
from asyncio import Queue

from src.bot_instance import BotInstance

async def telegram_sender_task(queue: Queue, bot_instance: BotInstance):
    """
    A self-contained, instance-aware task that connects MULTIPLE sender clients
    and sends messages from a queue.
    """
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("telegram", {})
    sender_session_names = creds.get("sender_bot_users", [])

    if not sender_session_names:
        print(f"[TELEGRAM_SENDER] Sender for user {user_id} cannot start: No sender_bot_users defined.")
        return

    sender_clients: dict[str, TelegramClient] = {}
    
    # Create all sender client objects
    for name in sender_session_names:
        api_id = creds.get(f"sender_{name}_api_id")
        api_hash = creds.get(f"sender_{name}_api_hash")
        if api_id and api_hash:
            session_path = os.path.join('data', 'sessions', f"{user_id}_{name}")
            sender_clients[name] = TelegramClient(session_path, int(api_id), api_hash)
        else:
            print(f"Warning: Missing credentials for sender '{name}' for user {user_id}.")

    if not sender_clients:
        print(f"[TELEGRAM_SENDER] No valid sender clients could be created for user {user_id}.")
        return

    try:
        # Connect all sender clients
        print(f"[TELEGRAM_SENDER] Connecting {len(sender_clients)} sender client(s) for user {user_id}...")
        await asyncio.gather(*(client.start() for client in sender_clients.values()))
        print(f"[TELEGRAM_SENDER] All sender clients for user {user_id} connected.")

        while True:
            msg = await queue.get()
            
            channel_id = msg.get("channel_id")
            text = msg.get("message")
            telegram_user = msg.get("telegram_user")

            if not all([channel_id, text, telegram_user]):
                print(f"[TELEGRAM_SENDER] User {user_id} skipping invalid payload: {msg}")
                queue.task_done()
                continue
            
            client_to_use = sender_clients.get(telegram_user)
            if client_to_use and client_to_use.is_connected():
                await client_to_use.send_message(int(channel_id), text)
                print(f"[TELEGRAM_SENDER] Message sent for user {user_id} via {telegram_user}.")
            else:
                print(f"[TELEGRAM_SENDER] Client for '{telegram_user}' not found or disconnected for user {user_id}.")

            min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 5.0)
            max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 15.0)
            await asyncio.sleep(random.uniform(min_delay, max_delay))
            
            queue.task_done()
            
    except asyncio.CancelledError:
        print(f"[TELEGRAM_SENDER] Task for user {user_id} cancelled.")
    except Exception as e:
        print(f"CRITICAL ERROR in Telegram Sender for user {user_id}: {e}")
    finally:
        print(f"[TELEGRAM_SENDER] Disconnecting sender clients for user {user_id}...")
        await asyncio.gather(*(client.disconnect() for client in sender_clients.values() if client.is_connected()))
        print(f"[TELEGRAM_SENDER] Sender clients for user {user_id} disconnected.")