# src/senders/discord_sender.py

import asyncio
from asyncio import Queue
import discord
import random

from src.bot_instance import BotInstance

async def discord_sender_task(
    queue: Queue, 
    bot_instance: BotInstance,
    shared_client_setup_event: asyncio.Event,
    shared_client_object: list
):
    """
    A dedicated worker that sends messages to Discord using the shared client
    from the listener task.
    """
    user_id = bot_instance.user_id
    print(f"[DISCORD SENDER] Worker for user {user_id} is waiting for client to be ready...")
    
    # Wait until the listener has successfully connected and set the event
    await shared_client_setup_event.wait()

    if not shared_client_object:
        print(f"[DISCORD SENDER] Could not start for user {user_id}: Listener failed to provide a client object.")
        return
        
    client: discord.Client = shared_client_object[0]
    print(f"[DISCORD SENDER] Worker for user {user_id} has received client and is starting.")

    while not client.is_closed():
        try:
            msg = await queue.get()
            
            channel_id_str = msg.get("channel_id")
            text = msg.get("message")

            if not all([channel_id_str, text]):
                queue.task_done()
                continue
            
            channel = client.get_channel(int(channel_id_str))
            
            if channel and isinstance(channel, discord.abc.Messageable):
                await channel.send(text)
                print(f"[DISCORD SENDER] Message sent for user {user_id} to channel {channel_id_str}.")
            else:
                print(f"[DISCORD SENDER] ERROR: Could not find channel with ID {channel_id_str} for user {user_id}.")

            min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 1.0)
            max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 3.0)
            await asyncio.sleep(random.uniform(min_delay, max_delay))
            
            queue.task_done()

        except asyncio.CancelledError:
            print(f"[DISCORD SENDER] Task cancelled for user {user_id}.")
            break
        except Exception as e:
            print(f"CRITICAL ERROR in Discord Sender for user {user_id}: {e}")
            await asyncio.sleep(5)