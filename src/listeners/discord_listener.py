# src/listeners/discord_listener.py

import discord
from asyncio import Queue
from src.core_logic.internal_message import InternalMessage

def setup_discord_listener(client: discord.Client, brain_queue: Queue, target_channel_id: str):
    """
    Sets up the event handler for the Discord client.
    """
    print("[DISCORD_LISTENER] Setting up event handler...")

    @client.event
    async def on_message(message: discord.Message):
        # 1. Ignore messages from bots (including ourself)
        if message.author.bot:
            return

        # 2. Ignore messages that are not from our target channel
        if str(message.channel.id) != target_channel_id:
            return
            
        # 3. Ensure the message has content
        if not message.content:
            return

        print(f"[DISCORD_LISTENER] Received Discord message: '{message.content[:50]}...'")

        # 4. Convert the Discord message into our standardized InternalMessage
        internal_msg = InternalMessage(
            platform='discord',
            channel_id=str(message.channel.id),
            message_id=str(message.id),
            text=message.content,
            sender_id=str(message.author.id)
        )
        
        # 5. Put the standardized message onto the brain queue
        await brain_queue.put(internal_msg)

    print("[DISCORD_LISTENER] Event handler registered.")