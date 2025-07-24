# src/listeners/slack_listener.py

import asyncio
from slack_bolt.async_app import AsyncApp
from src.core_logic.internal_message import InternalMessage
from asyncio import Queue

async def slack_listener_worker(app: AsyncApp, brain_queue: Queue, target_channel_id: str):
    """
    A dedicated worker that listens for Slack messages, converts them,
    and puts them on the brain_queue.
    """
    print("[SLACK_LISTENER] Worker started.")
    
    # CORRECTED: Use the more general "message" event handler
    @app.event("message")
    async def handle_message_events(body: dict, logger):
        """
        This function is triggered for ANY new message event the bot can see.
        """
        event = body.get("event", {})
        
        # --- We now check the channel ID inside the handler ---
        channel_id = event.get("channel")
        
        # 1. Ignore messages that are not from our target channel
        if channel_id != target_channel_id:
            return

        # 2. Ignore messages from bots (including ourself) to prevent loops
        if event.get("bot_id"):
            return
            
        text = event.get("text")
        if not text:
            return

        print(f"[SLACK_LISTENER] Received Slack message in target channel: '{text[:50]}...'")

        # Convert the Slack message into our standardized InternalMessage format
        internal_msg = InternalMessage(
            platform='slack',
            channel_id=str(channel_id),
            message_id=str(event.get("client_msg_id", event.get("ts"))),
            text=str(text),
            sender_id=str(event.get("user"))
        )
        
        # Put the standardized message onto the brain queue for processing
        await brain_queue.put(internal_msg)

    print("[SLACK_LISTENER] General message handler registered.")