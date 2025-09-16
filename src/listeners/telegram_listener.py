# src/listeners/telegram_listener.py

import asyncio
from telethon import TelegramClient, events
from asyncio import Queue, AbstractEventLoop
from telethon.sessions import StringSession

from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

def run_telethon_in_thread(
    client: TelegramClient, 
    bot_instance: BotInstance, 
    brain_queue: Queue, 
    main_loop: AbstractEventLoop
):
    """A synchronous function that runs the entire Telethon lifecycle in a new thread."""
    # This function now gets its OWN loop, which is critical for shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    user_id = bot_instance.user_id

    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event):
        # ... (handler logic remains the same) ...
        message = event.message
        target_group_id = str(bot_instance.credentials.get("telegram", {}).get("telegram_group_id"))
        
        if not message or not message.text or str(message.chat_id) != target_group_id:
            return
            
        print(f"[TELEGRAM-LISTENER-THREAD] User {user_id} received message: '{message.text[:50]}...'")
        
        internal_msg = InternalMessage(
            platform='telegram', channel_id=str(message.chat_id),
            message_id=str(message.id), text=message.text,
            sender_id=str(getattr(message, 'sender_id', 'unknown'))
        )
        main_loop.call_soon_threadsafe(brain_queue.put_nowait, internal_msg)

    print(f"[TELEGRAM-LISTENER-THREAD] Connecting for user {user_id}...")
    with client:
        print(f"[TELEGRAM-LISTENER-THREAD] Connected. Listening for messages...")
        client.run_until_disconnected()
    print(f"[TELEGRAM-LISTENER-THREAD] Disconnected.")


async def telegram_listener_task(brain_queue: Queue, bot_instance: BotInstance):
    user_id = bot_instance.user_id
    print(f"\n--- [TELEGRAM LISTENER] Main task starting for {user_id} ---")
    
    client = None # Define client in the outer scope
    try:
        tg_config = bot_instance.credentials.get("telegram", {})
        ingestor_config = tg_config.get("ingestor_config", {})
        api_id, api_hash, session_string = (
            ingestor_config.get("api_id"), ingestor_config.get("api_hash"),
            ingestor_config.get("session_string")
        )
        
        if not all([api_id, api_hash, session_string]):
            print(f"  -> FATAL: [TELEGRAM LISTENER] Missing credentials for {user_id}. Task exiting.")
            return

        main_event_loop = asyncio.get_running_loop()
        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        
        print(f"[TELEGRAM LISTENER] Offloading Telethon client for {user_id} to a dedicated thread...")
        await asyncio.to_thread(
            run_telethon_in_thread,
            client,
            bot_instance,
            brain_queue,
            main_event_loop
        )

    except asyncio.CancelledError:
        print(f"[TELEGRAM LISTENER] Main task for {user_id} cancelled.")
    except Exception as e:
        print(f"CRITICAL ERROR in Telegram Listener Task for {user_id}: {e}")
    finally:
        # --- THIS IS THE FIX FOR CLEAN SHUTDOWN ---
        # If the client was created and is connected, we must disconnect it.
        if client and client.is_connected():
            print("[TELEGRAM LISTENER] Disconnecting client from main task...")
            # This is a coroutine, so we await it.
            await client.disconnect()
        # --- END OF FIX ---
        print(f"[TELEGRAM LISTENER] Main task for {user_id} has finished.")