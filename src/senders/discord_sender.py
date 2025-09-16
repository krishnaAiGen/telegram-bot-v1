# src/senders/discord_sender.py

import asyncio
from asyncio import Queue
from src.bot_instance import BotInstance

async def discord_sender_task(
    sender_queue: Queue,
    bot_instance: BotInstance,
    command_queue: Queue  # We now require the new command_queue
):
    """
    This worker's ONLY job is to take a message from the brain's sender_queue
    and put it onto the listener's internal command_queue. This decouples
    the brain from the live discord client.
    """
    user_id = bot_instance.user_id
    print(f"[DISCORD SENDER] Bridge worker starting for user {user_id}.")
    
    while True:
        try:
            # 1. Get the payload from the brain
            payload = await sender_queue.get()
            
            # 2. Put the payload onto the command queue for the listener to handle
            await command_queue.put(payload)
            
            print(f"[DISCORD SENDER] Relayed message for user {user_id} to listener's command queue.")
            
            sender_queue.task_done()

        except asyncio.CancelledError:
            print(f"[DISCORD SENDER] Bridge worker for user {user_id} cancelled.")
            break
        except Exception as e:
            print(f"CRITICAL ERROR in Discord Sender Bridge for user {user_id}: {e}")
            await asyncio.sleep(5)