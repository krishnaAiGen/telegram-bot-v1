# src/listeners/telegram_listener.py

import asyncio
from telethon import events
from src.core_logic.internal_message import InternalMessage

async def telegram_listener_worker(client: events.NewMessage.Event, brain_queue: asyncio.Queue, group_id: int):
    """
    A dedicated worker that listens for Telegram messages, converts them,
    and puts them on the brain_queue.
    """
    print("[TELEGRAM_LISTENER] Worker started.")
    
    @client.on(events.NewMessage(chats=[group_id]))
    async def handler(event: events.NewMessage.Event):
        message = event.message
        if not message or not message.text:
            return

        print(f"[TELEGRAM_LISTENER] Received Telegram message: '{message.text[:50]}...'")

        # Create the InternalMessage, ensuring all IDs are strings.
        # This fixes the potential bugs.
        internal_msg = InternalMessage(
            platform='telegram',
            channel_id=str(message.chat_id),
            message_id=str(message.id),
            text=message.text,
            sender_id=str(getattr(message, 'sender_id', 'unknown'))
        )
        
        await brain_queue.put(internal_msg)
    
    # The worker's job is to keep the client running.
    # The client.run_until_disconnected() in main.py handles this.
    await client.run_until_disconnected()