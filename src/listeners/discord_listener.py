# File: src/listeners/discord_listener.py

import discord
import asyncio
import logging
from asyncio import Queue
from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance
import random

logger = logging.getLogger(__name__)

async def discord_listener_task(
    brain_queue: Queue, 
    bot_instance: BotInstance,
    command_queue: Queue
):
    user_id = bot_instance.user_id
    creds = bot_instance.credentials.get("discord", {})
    bot_token, target_channel_id = creds.get("bot_token"), creds.get("channel_id")

    if not all([bot_token, target_channel_id]):
        logger.critical(f"FATAL for user {user_id}: missing Discord credentials. Listener task cannot start.")
        return

    main_loop = asyncio.get_running_loop()
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    
    client = discord.Client(intents=intents)

    async def sender_coro():
        logger.info(f"Internal Discord sender coroutine started for user {user_id}.")
        while not client.is_closed():
            try:
                payload = await command_queue.get()
                logger.debug(f"Sender coro for {user_id} received payload: {payload}")
                
                channel_id_str = payload.get("channel_id")
                text = payload.get("message")

                if not all([channel_id_str, text]):
                    logger.warning(f"Sender coro for {user_id} skipping invalid payload: {payload}")
                    command_queue.task_done()
                    continue
                
                channel = client.get_channel(int(channel_id_str))
                
                if channel and isinstance(channel, discord.abc.Messageable):
                    min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 1.0)
                    max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 3.0)
                    delay = random.uniform(min_delay, max_delay)
                    logger.debug(f"Sender coro for {user_id} delaying for {delay:.2f} seconds.")
                    await asyncio.sleep(delay)
                    
                    await channel.send(text)
                    logger.info(f"Message sent to Discord for user {user_id}.")
                else:
                    logger.error(f"Sender coro for {user_id} could not find a messageable channel with ID {channel_id_str}.")
                
                command_queue.task_done()
            except Exception:
                logger.critical(f"CRITICAL ERROR in Discord Sender Coro for user {user_id}", exc_info=True)

    @client.event
    async def on_ready():
        logger.info(f"Discord client connected as {client.user} for user {user_id}.")
        asyncio.create_task(sender_coro())

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            logger.debug(f"Ignoring message from bot {message.author} for user {user_id}.")
            return
        if str(message.channel.id) != target_channel_id:
            logger.debug(f"Ignoring message from wrong channel for user {user_id}.")
            return
        if not message.content:
            logger.debug(f"Ignoring message with no content for user {user_id}.")
            return
        
        logger.debug(f"Received Discord message '{message.content[:50]}...' for user {user_id}.")
        internal_msg = InternalMessage(
            platform='discord', channel_id=str(message.channel.id),
            message_id=str(message.id), text=message.content,
            sender_id=str(message.author.id)
        )
        
        logger.debug(f"Putting message for {user_id} onto brain queue ID: {id(brain_queue)}")
        main_loop.call_soon_threadsafe(brain_queue.put_nowait, internal_msg)

    try:
        await client.start(bot_token)
    except asyncio.CancelledError:
        logger.info(f"Discord listener task cancelled for user {user_id}.")
    except Exception:
        logger.critical(f"CRITICAL ERROR in Discord Listener for {user_id}", exc_info=True)
    finally:
        if client and not client.is_closed():
            await client.close()
        logger.info(f"Discord listener disconnected for user {user_id}.")