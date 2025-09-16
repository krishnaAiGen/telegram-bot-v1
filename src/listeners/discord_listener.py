# src/listeners/discord_listener.py

import discord
import asyncio
from asyncio import Queue
from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance
import random

async def discord_listener_task(
    brain_queue: Queue, 
    bot_instance: BotInstance,
    command_queue: Queue # The listener now also gets the command_queue
):
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("discord", {})
    bot_token, target_channel_id = creds.get("bot_token"), creds.get("channel_id")

    if not all([bot_token, target_channel_id]):
        print(f"[DISCORD LISTENER] FATAL for user {user_id}: missing credentials.")
        return

    main_loop = asyncio.get_running_loop()
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    
    client = discord.Client(intents=intents)

    # This is the new sending logic, running safely inside the listener
    async def sender_coro():
        print("[DISCORD SENDER CORO] Starting internally within listener...")
        while not client.is_closed():
            try:
                payload = await command_queue.get()
                channel_id_str = payload.get("channel_id")
                text = payload.get("message")

                if not all([channel_id_str, text]):
                    command_queue.task_done()
                    continue
                
                channel = client.get_channel(int(channel_id_str))
                
                if channel and isinstance(channel, discord.abc.Messageable):
                    min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 1.0)
                    max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 3.0)
                    await asyncio.sleep(random.uniform(min_delay, max_delay))
                    await channel.send(text)
                    print(f"[DISCORD SENDER CORO] Message sent for user {user_id}.")
                else:
                    print(f"[DISCORD SENDER CORO] ERROR: Could not find channel {channel_id_str}.")
                
                command_queue.task_done()
            except Exception as e:
                print(f"CRITICAL ERROR in Discord Sender Coro: {e}")

    @client.event
    async def on_ready():
        print(f"[DISCORD LISTENER] Connected as {client.user} for user {user_id}.")
        # Start the internal sender coroutine once the client is ready
        asyncio.create_task(sender_coro())

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot or str(message.channel.id) != target_channel_id or not message.content:
            return
        
        internal_msg = InternalMessage(
            platform='discord', channel_id=str(message.channel.id),
            message_id=str(message.id), text=message.content,
            sender_id=str(message.author.id)
        )
        main_loop.call_soon_threadsafe(brain_queue.put_nowait, internal_msg)

    try:
        # The client.start() method is now used, which is better for this pattern
        await client.start(bot_token)
    except asyncio.CancelledError:
        print(f"[DISCORD LISTENER] Task cancelled for user {user_id}.")
    except Exception as e:
        print(f"CRITICAL ERROR in Discord Listener for {user_id}: {e}")
    finally:
        if not client.is_closed():
            await client.close()
        print(f"[DISCORD LISTENER] Disconnected for user {user_id}.")