# src/listeners/telegram_listener.py

import asyncio
import os
from telethon import TelegramClient, events
from asyncio import Queue

from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

async def telegram_listener_task(brain_queue: Queue, bot_instance: BotInstance):
    """
    A self-contained, instance-aware task that connects to Telegram as the
    ingestor bot and listens for messages.
    """
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("telegram", {})
    ingestor_session_name = creds.get("ingestor_bot_user", f"default_ingestor_{user_id}")
    
    api_id = creds.get(f"ingestor_api_id")
    api_hash = creds.get(f"ingestor_api_hash")
    group_id = bot_instance.behavior_settings.get("telegram_group_id")

    if not all([api_id, api_hash, group_id]):
        print(f"[TELEGRAM_LISTENER] Ingestor for user {user_id} cannot start: missing api_id, api_hash, or group_id.")
        return

    # Create a unique path for this user's session file
    session_path = os.path.join('data', 'sessions', f"{user_id}_{ingestor_session_name}")
    
    client = TelegramClient(session_path, int(api_id), api_hash)
    print(f"[TELEGRAM_LISTENER] Client created for user {user_id}.")

    @client.on(events.NewMessage(chats=[int(group_id)]))
    async def handler(event: events.NewMessage.Event):
        message = event.message
        if not message or not message.text:
            return

        print(f"[TELEGRAM_LISTENER] User {user_id} received message: '{message.text[:50]}...'")

        internal_msg = InternalMessage(
            platform='telegram',
            channel_id=str(message.chat_id),
            message_id=str(message.id),
            text=message.text,
            sender_id=str(getattr(message, 'sender_id', 'unknown'))
        )
        await brain_queue.put(internal_msg)

    try:
        print(f"[TELEGRAM_LISTENER] Connecting ingestor for user {user_id}...")
        await client.start()
        print(f"[TELEGRAM_LISTENER] Ingestor for user {user_id} connected. Listening for messages...")
        await client.run_until_disconnected()
    except asyncio.CancelledError:
        print(f"[TELEGRAM_LISTENER] Task for user {user_id} cancelled.")
    except Exception as e:
        print(f"CRITICAL ERROR in Telegram Listener for user {user_id}: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
        print(f"[TELEGRAM_LISTENER] Ingestor for user {user_id} disconnected.")