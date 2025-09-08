# src/listeners/slack_listener.py

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from asyncio import Queue

from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

async def slack_listener_task(brain_queue: Queue, bot_instance: BotInstance):
    """A self-contained task that connects to Slack and listens for messages."""
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("slack", {})
    bot_token = creds.get("bot_token")
    app_token = creds.get("app_token")
    
    target_channel_id = creds.get("channel_id")

    if not all([bot_token, app_token, target_channel_id]):
        print(f"[SLACK LISTENER] Cannot start for user {user_id}: missing credentials.")
        return

    app = AsyncApp(token=bot_token)
    
    @app.event("message")
    async def handle_message_events(body: dict, say):
        event = body.get("event", {})
        channel_id = event.get("channel")
        if channel_id != target_channel_id or event.get("bot_id"):
            return
        
        text = event.get("text")
        if not text:
            return
        
        print(f"[SLACK LISTENER] User {user_id} received message: '{text[:50]}...'")

        internal_msg = InternalMessage(
            platform='slack',
            channel_id=str(channel_id),
            message_id=str(event.get("client_msg_id", event.get("ts"))),
            text=str(text),
            sender_id=str(event.get("user"))
        )
        await brain_queue.put(internal_msg)

    handler = AsyncSocketModeHandler(app, app_token)
    try:
        print(f"[SLACK LISTENER] Connecting for user {user_id}...")
        await handler.start_async()
    except Exception as e:
        print(f"CRITICAL ERROR in Slack Listener for user {user_id}: {e}")
    finally:
        print(f"[SLACK LISTENER] Disconnected for user {user_id}.")