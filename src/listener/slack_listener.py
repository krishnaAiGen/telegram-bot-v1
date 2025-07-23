# src/listeners/slack_listener.py

import asyncio
from slack_bolt.async_app import AsyncApp
from src.core_logic.internal_message import InternalMessage

async def slack_listener_worker(app: AsyncApp, brain_queue: asyncio.Queue, channel_id: str):
    """
    A dedicated worker that listens for Slack messages, converts them,
    and puts them on the brain_queue.
    """
    print("[SLACK_LISTENER] Worker started.")
    
    @app.message(channel_id)
    async def handle_messages(body, say):
        event = body.get("event", {})
        text = event.get("text")
        
        if event.get("bot_id"):
            return
        if not text:
            return

        print(f"[SLACK_LISTENER] Received Slack message: '{text[:50]}...'")

        # Slack IDs are already strings, but we ensure consistency.
        internal_msg = InternalMessage(
            platform='slack',
            channel_id=str(event.get("channel")),
            message_id=str(event.get("client_msg_id", event.get("ts"))), # Use ts as fallback
            text=str(text),
            sender_id=str(event.get("user"))
        )
        
        await brain_queue.put(internal_msg)

    # Handled by app.start() in main.py
    # We need the listener to be active. This function can essentially 'end'
    # after setup, as the @app.message decorator has registered the handler.
    # The main loop is managed by slack_bolt itself.
    print("[SLACK_LISTENER] Message handler registered.")