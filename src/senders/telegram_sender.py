# src/senders/telegram_sender.py

import asyncio
import random
from telethon import TelegramClient
from asyncio import Queue
from telethon.sessions import StringSession

from src.bot_instance import BotInstance

async def telegram_sender_task(queue: Queue, bot_instance: BotInstance):
    user_id = bot_instance.user_id
    print(f"\n--- DEBUG: [TELEGRAM SENDER] Task starting for user: {user_id} ---")
    
    tg_config = bot_instance.credentials.get("telegram", {})
    senders_config = tg_config.get("senders_config", {})
    print(f"  -> Senders specific config: {senders_config}")

    if not senders_config:
        print(f"  -> FATAL: No senders_config defined for user {user_id}. Exiting task.")
        return

    sender_clients: dict[str, TelegramClient] = {}
    
    for name, config in senders_config.items():
        print(f"    -> Processing sender '{name}' with config: {config}")
        api_id = config.get("api_id")
        api_hash = config.get("api_hash")
        session_string = config.get("session_string")
        if all([api_id, api_hash, session_string]):
            print(f"      -> Credentials valid for '{name}'. Creating client.")
            session = StringSession(session_string)
            sender_clients[name] = TelegramClient(session, int(api_id), api_hash)
        else:
            print(f"      -> WARNING: Missing full credentials for sender '{name}'. It will be skipped.")

    if not sender_clients:
        print(f"[TELEGRAM_SENDER] No valid sender clients could be created for user {user_id}. Exiting task.")
        return

    try:
        print(f"[TELEGRAM_SENDER] Connecting {len(sender_clients)} sender client(s) for user {user_id}...")
        for name, client in list(sender_clients.items()):
            try:
                print(f"  -> Attempting to start client '{name}'...")
                await asyncio.wait_for(client.start(), timeout=30.0) 
                print(f"  -> Client '{name}' connected successfully.")
            except Exception as e:
                print(f"  -> CRITICAL STARTUP ERROR for client '{name}': {e}")
                del sender_clients[name]
        
        if not sender_clients:
            print(f"[TELEGRAM_SENDER] All sender clients failed to connect for user {user_id}. Exiting task.")
            return

        print(f"[TELEGRAM_SENDER] Finished connection attempts for user {user_id}. {len(sender_clients)} client(s) are active.")

        while True:
            try:
                msg = await queue.get()
                print(f"[TELEGRAM SENDER] DEBUG: Received payload from queue: {msg}")

                try:
                    channel_id = msg.get("channel_id")
                    text = msg.get("message")
                    
                    if not all([channel_id, text]):
                        print(f"[TELEGRAM SENDER] Skipping invalid payload (missing channel or text): {msg}")
                        continue
                    
                    telegram_user_name = msg.get("telegram_user")
                    client_to_use = sender_clients.get(telegram_user_name)

                    # --- THIS IS THE FINAL FIX ---
                    # If the requested client name is missing OR no client was specified (it's None),
                    # and we have at least one client available, use one as a fallback.
                    if not client_to_use and len(sender_clients) >= 1:
                        # Pick the first available client from the dictionary
                        fallback_name = list(sender_clients.keys())[0]
                        client_to_use = sender_clients[fallback_name]
                        print(f"  -> WARNING: Client for '{telegram_user_name}' not found or not specified. Falling back to the first available client: '{fallback_name}'.")
                    # --- END OF FIX ---
                    
                    if client_to_use and client_to_use.is_connected():
                        me = await client_to_use.get_me()
                        sender_name = me.username or me.first_name
                        await client_to_use.send_message(int(channel_id), text)
                        print(f"[TELEGRAM SENDER] Message sent for user {user_id} via {sender_name}.")
                    else:
                        print(f"CRITICAL ERROR: Could not find a valid, connected client to send the message for user {user_id}.")

                    min_delay = bot_instance.behavior_settings.get("min_send_delay_secs", 5.0)
                    max_delay = bot_instance.behavior_settings.get("max_send_delay_secs", 15.0)
                    await asyncio.sleep(random.uniform(min_delay, max_delay))

                except Exception as e:
                    print(f"CRITICAL SEND ERROR in Telegram Sender for user {user_id}: {e}")
                
                finally:
                    queue.task_done()

            except asyncio.CancelledError:
                print(f"[TELEGRAM_SENDER] Task for user {user_id} cancelled.")
                break
            except Exception as e:
                print(f"FATAL ERROR in Telegram Sender main loop for user {user_id}: {e}")
                await asyncio.sleep(5)
            
    except Exception as e:
        print(f"CRITICAL ERROR in Telegram Sender main task for user {user_id}: {e}")
    finally:
        print(f"[TELEGRAM_SENDER] Disconnecting sender clients for user {user_id}...")
        await asyncio.gather(*(client.disconnect() for client in sender_clients.values() if client.is_connected()), return_exceptions=True)
        print(f"[TELEGRAM_SENDER] Sender clients for user {user_id} disconnected.")