# src/senders/discord_sender.py

import asyncio
from asyncio import Queue
import discord
from config.settings import APP_CONFIG
import random

async def discord_sender_worker(queue: Queue, client: discord.Client):
    """
    A dedicated worker that listens on a queue and sends messages to Discord.
    """
    print("[DISCORD_SENDER] Worker started.")
    while True:
        try:
            msg = await queue.get()
            
            channel_id_str = msg.get("channel_id")
            text = msg.get("message")

            if not all([channel_id_str, text]):
                print(f"[DISCORD_SENDER] Skipping invalid message payload: {msg}")
                queue.task_done()
                continue
            
            # discord.py needs the channel ID as an integer
            channel = client.get_channel(int(channel_id_str))
            
            if channel and isinstance(channel, discord.abc.Messageable):
                await channel.send(text)
                print(f"[DISCORD_SENDER] Message sent successfully to channel {channel_id_str}.")
            else:
                print(f"[DISCORD_SENDER] ERROR: Could not find a messageable channel with ID {channel_id_str}.")

            # Optional delay to prevent rate-limiting
            await asyncio.sleep(random.uniform(1.0, 3.0)) # Discord can be sensitive to rate limits
            queue.task_done()

        except Exception as e:
            print(f"CRITICAL ERROR in Discord Sender Worker: {e}")
            await asyncio.sleep(10)