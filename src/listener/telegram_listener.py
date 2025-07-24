# src/listeners/telegram_listener.py

import asyncio
from telethon import TelegramClient, events
from src.core_logic.internal_message import InternalMessage
from asyncio import Queue

def telegram_listener_worker(client: TelegramClient, brain_queue: Queue, group_id: int):
    """
    Sets up the event handler for the Telegram client.
    This function doesn't run the client, it just prepares it.
    """
    print("[TELEGRAM_LISTENER] Setting up event handler...")
    
    @client.on(events.NewMessage(chats=[group_id]))
    async def handler(event: events.NewMessage.Event):
        message = event.message
        if not message or not message.text:
            return

        print(f"[TELEGRAM_LISTENER] Received Telegram message: '{message.text[:50]}...'")

        internal_msg = InternalMessage(
            platform='telegram',
            channel_id=str(message.chat_id),
            message_id=str(message.id),
            text=message.text,
            sender_id=str(getattr(message, 'sender_id', 'unknown'))
        )
        
        await brain_queue.put(internal_msg)

    print("[TELEGRAM_LISTENER] Event handler registered.")