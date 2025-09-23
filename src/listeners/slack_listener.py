# File: src/listeners/slack_listener.py

import asyncio
import logging
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from asyncio import Queue

from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

logger = logging.getLogger(__name__)

async def slack_listener_task(brain_queue: Queue, bot_instance: BotInstance):
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("slack", {})
    bot_token, app_token, target_channel_id = (
        creds.get("bot_token"), creds.get("app_token"), creds.get("channel_id")
    )

    if not all([bot_token, app_token, target_channel_id]):
        logger.critical(f"Cannot start Slack listener for user {user_id}: missing credentials.")
        return

    app = AsyncApp(token=bot_token)
    handler = AsyncSocketModeHandler(app, app_token)
    
    @app.event("message")
    async def handle_message_events(body: dict, say):
        event = body.get("event", {})
        
        if event.get("channel") != target_channel_id:
            logger.debug("Slack listener ignoring message from wrong channel.")
            return
        if event.get("bot_id") or event.get("subtype"):
            logger.debug("Slack listener ignoring bot message or event subtype.")
            return
        
        text = event.get("text")
        if not text:
            logger.debug("Slack listener ignoring message with no text.")
            return
        
        logger.info(f"Received Slack message for user {user_id}: '{text[:50]}...'")
        internal_msg = InternalMessage(
            platform='slack', channel_id=str(event.get("channel")),
            message_id=str(event.get("client_msg_id", event.get("ts"))),
            text=str(text), sender_id=str(event.get("user"))
        )
        
        logger.debug(f"Putting message for {user_id} onto brain queue ID: {id(brain_queue)}")
        await brain_queue.put(internal_msg)
        logger.debug(f"Successfully put Slack message on queue for user {user_id}.")

    try:
        logger.info(f"Connecting Slack listener for user {user_id}...")
        await handler.start_async()
        logger.info(f"Slack Bolt app is running for user {user_id}.")
        await asyncio.Event().wait() 
    except asyncio.CancelledError:
        logger.info(f"Slack listener task cancelled for user {user_id}.")
    except Exception:
        logger.critical(f"CRITICAL ERROR in Slack Listener for user {user_id}", exc_info=True)
    finally:
        logger.info(f"Stopping Slack handler for user {user_id}...")
        await handler.stop()
        logger.info(f"Slack listener disconnected for user {user_id}.")