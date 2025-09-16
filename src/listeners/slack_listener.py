# In src/listeners/slack_listener.py

import asyncio
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from asyncio import Queue

from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

async def slack_listener_task(brain_queue: Queue, bot_instance: BotInstance):
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("slack", {})
    bot_token, app_token, target_channel_id = (
        creds.get("bot_token"), creds.get("app_token"), creds.get("channel_id")
    )

    if not all([bot_token, app_token, target_channel_id]):
        print(f"[SLACK LISTENER] Cannot start for user {user_id}: missing credentials.")
        return

    app = AsyncApp(token=bot_token)
    handler = AsyncSocketModeHandler(app, app_token)
    
    @app.event("message")
    async def handle_message_events(body: dict, say):
        event = body.get("event", {})
        # Added a check for 'subtype' to ignore channel joins, etc.
        if event.get("channel") != target_channel_id or event.get("bot_id") or event.get("subtype"): 
            return
        
        text = event.get("text")
        if not text: return
        
        print(f"[SLACK LISTENER] User {user_id} received message: '{text[:50]}...'")
        internal_msg = InternalMessage(
            platform='slack', channel_id=str(event.get("channel")),
            message_id=str(event.get("client_msg_id", event.get("ts"))),
            text=str(text), sender_id=str(event.get("user"))
        )
        await brain_queue.put(internal_msg)

    try:
        print(f"[SLACK LISTENER] Connecting for user {user_id}...")
        # handler.start_async() starts background tasks. We just need to keep this task alive.
        await handler.start_async()
        # This will wait indefinitely until the task is cancelled.
        await asyncio.Event().wait() 
    except asyncio.CancelledError:
        print(f"[SLACK LISTENER] Task cancelled for user {user_id}.")
    except Exception as e:
        print(f"CRITICAL ERROR in Slack Listener for user {user_id}: {e}")
    finally:
        # --- THIS IS THE FIX FOR THE SHUTDOWN ERROR ---
        # Explicitly stop the handler to allow its background tasks to clean up.
        print("[SLACK LISTENER] Stopping handler...")
        await handler.stop()
        # --- END OF FIX ---
        print(f"[SLACK LISTENER] Disconnected for user {user_id}.")