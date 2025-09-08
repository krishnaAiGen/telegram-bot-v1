# src/listeners/discord_listener.py

import discord
import asyncio
from asyncio import Queue

from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

async def discord_listener_task(
    brain_queue: Queue, 
    bot_instance: BotInstance,
    shared_client_setup_event: asyncio.Event,
    shared_client_object: list
):
    """
    A self-contained task that connects to Discord and listens for messages.
    It also shares the live client object for the sender to use.
    """
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("discord", {})
    bot_token = creds.get("bot_token")
    target_channel_id = creds.get("channel_id")

    if not all([bot_token, target_channel_id]):
        print(f"[DISCORD LISTENER] Cannot start for user {user_id}: missing credentials.")
        shared_client_setup_event.set() # Signal that setup is done (failed)
        return

    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        """Event that fires once the client is connected and ready."""
        print(f"[DISCORD LISTENER] Connected as {client.user} for user {user_id}.")
        # Store the ready client and signal the event
        shared_client_object.append(client)
        shared_client_setup_event.set()

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot or str(message.channel.id) != target_channel_id or not message.content:
            return

        print(f"[DISCORD LISTENER] User {user_id} received message: '{message.content[:50]}...'")
        
        internal_msg = InternalMessage(
            platform='discord',
            channel_id=str(message.channel.id),
            message_id=str(message.id),
            text=message.content,
            sender_id=str(message.author.id)
        )
        await brain_queue.put(internal_msg)

    try:
        print(f"[DISCORD LISTENER] Connecting for user {user_id}...")
        # The start method is blocking, so it must be the last thing in the try block
        await client.start(bot_token)
    except asyncio.CancelledError:
        print(f"[DISCORD LISTENER] Task cancelled for user {user_id}.")
    except Exception as e:
        print(f"CRITICAL ERROR in Discord Listener for user {user_id}: {e}")
        shared_client_setup_event.set() # Signal failure so sender doesn't wait forever
    finally:
        if not client.is_closed():
            await client.close()
        print(f"[DISCORD LISTENER] Disconnected for user {user_id}.")