# src/workers/brain.py

import asyncio
import time
import random
from asyncio import Queue 

from src.services.fetch_db import save_message_to_db
from src.services.openai_chat import get_llm_response
from src.core_logic.response_logic import handle_reaction, handle_initiation, handle_realtime_query
from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

async def brain_worker(brain_queue: Queue, sender_queues: dict[str, Queue], bot_instance: BotInstance, db: any):    
    print(f"[BRAIN-DEBUG] Worker started for user: {bot_instance.user_id}")
    print(f"--- [BRAIN-DEBUG] I am consuming from Brain Queue with ID: {id(brain_queue)} ---")
    
    state_manager = bot_instance.state_manager
    
    while True:
        try:
            print("[BRAIN-DEBUG] Top of main loop. ABOUT TO AWAIT brain_queue.get()")
            
            # Use a timeout to see if the loop is spinning without receiving messages.
            message: InternalMessage = await asyncio.wait_for(brain_queue.get(), timeout=5.0)
            
            print("\n======================================================================")
            print(f" [BRAIN-DEBUG] SUCCESS! MESSAGE RECEIVED FROM QUEUE!")
            print(f" [BRAIN-DEBUG] Platform: {message.platform}, Text: '{message.text[:50]}...'")
            print("======================================================================\n")
            
            bot_state = state_manager.load_bot_state()

            if state_manager.has_processed(message.message_id):
                print(f"[BRAIN] Message ID {message.message_id} already processed. Skipping.")
                brain_queue.task_done()
                continue
            
            save_message_to_db(message, user_id=bot_instance.user_id, db=db)

            # Get the Telegram-specific credentials
            telegram_creds = bot_instance.credentials.get("telegram", {})
            # Look for known_bot_ids within the Telegram credentials
            known_bot_ids = telegram_creds.get("known_bot_ids", [])

            # Get the IDs of our own sender accounts to also ignore them
            senders_config = telegram_creds.get("senders_config", {})
            own_sender_ids = [str(config.get("user_id")) for config in senders_config.values() if "user_id" in config]

            # Combine the lists and ensure all IDs are strings for safe comparison
            all_ids_to_ignore = [str(bid) for bid in known_bot_ids] + own_sender_ids

            if message.sender_id in all_ids_to_ignore:
                print(f"[BRAIN] Ignoring message from known bot/own sender ID: {message.sender_id}")
                state_manager.log_processed(message.message_id)
                brain_queue.task_done()
                continue
            
            print(f"[BRAIN] Triage: Analyzing message ID {message.message_id}...")
            triage_prompt = f"""Prompt Structure:
ROLE: "You are a hyper-efficient routing agent. Your only job is to classify an incoming user message into one of two categories: REALTIME_FACTS or PERSONA_OPINION."
CATEGORY DEFINITIONS:
REALTIME_FACTS: Define this category. It's for queries that require live, up-to-the-minute data. Provide keywords and examples:
Keywords: "price," "latest news," "what's happening with," "current sentiment," "did [X] just announce," "live chart."
Examples:
"What's the current price of ETH?" -> REALTIME_FACTS
"Did the Fed just release new inflation data?" -> REALTIME_FACTS
"What's the community sentiment on the new Solana update on X?" -> REALTIME_FACTS
PERSONA_OPINION: Define this category. It's for queries that require a personality, opinion, experience, or general knowledge. Provide keywords and examples:
Keywords: "what do you think," "is it a good idea," "how does this work," "in your experience," "can you explain," "I feel like."
Crucially, include persona-specific examples:
"What do you think of the new token standard? Does it remind you of 2017?" (This is an opinion question for the "Crypto OG" persona) -> PERSONA_OPINION
"Can someone explain how this new DeFi protocol's tokenomics work?" (This is a knowledge question for the "Token Economist" persona) -> PERSONA_OPINION
"I'm new here, how are you all doing?" (This is a social interaction for the "Community Builder" persona) -> PERSONA_OPINION
THE DECISION RULE: "If the user is asking for an objective, verifiable fact that could have changed in the last 24 hours, classify it as REALTIME_FACTS. For everything else—including opinions on current events, explanations, historical context, and social chat—classify it as PERSONA_OPINION."
THE TASK: "Classify the following user message. Respond with ONLY the single word REALTIME_FACTS or PERSONA_OPINION and nothing else."
USER MESSAGE: {message.text}"
"""             
            openai_api_key = bot_instance.credentials.get("openai", {}).get("api_key")
            triage_model = bot_instance.behavior_settings.get("triage_model", "gpt-3.5-turbo")
            if not openai_api_key:
                print(f"CRITICAL: OpenAI key not found during triage.")
                decision = "PERSONA_OPINION"
            else:
                decision = await get_llm_response(triage_prompt, api_key=openai_api_key, model=triage_model, max_tokens=5)
            
            print(f"[BRAIN] Triage decision: '{decision}'")
            
            response_payload = None

            if "REALTIME_FACTS" in decision:
                response_payload = await handle_realtime_query(message, bot_instance, db) 
            else:
                response_rate = bot_instance.behavior_settings.get("random_response_rate", 1.0)
                if random.random() < response_rate:
                    print(f"[BRAIN] Probability gate passed. Generating reaction.")
                    response_payload = await handle_reaction(message, bot_instance, db)
                else:
                    print(f"[BRAIN] Probability gate failed. Skipping reply.")

            if response_payload:
                platform = response_payload.get("platform")
                sender_queue = sender_queues.get(f"{platform}_sender_queue")
                if sender_queue:
                    await sender_queue.put(response_payload)
                    print(f"[BRAIN] Dispatched response payload to {platform} sender.")
                else:
                    print(f"[BRAIN] ERROR: No sender queue found for platform '{platform}'.")

            state_manager.log_processed(message.message_id)
            bot_state["last_activity_time"] = time.time()
            state_manager.save_bot_state(bot_state)
            brain_queue.task_done()

        except asyncio.TimeoutError:
            # If you see this message, the brain is alive but the queue is empty.
            print("[BRAIN-DEBUG] Timed out after 5s. No message on queue. Checking for topic initiation...")
            
            # Check if we should initiate a conversation
            bot_state = state_manager.load_bot_state()
            last_activity = bot_state.get("last_activity_time", 0)
            min_initiate_hours = bot_instance.behavior_settings.get("min_initiate_hours", 2)
            
            # Only initiate if enough time has passed since last activity
            if time.time() - last_activity > (min_initiate_hours * 3600):
                print(f"[BRAIN] {min_initiate_hours} hours since last activity. Attempting topic initiation...")
                
                try:
                    initiation_payload = await handle_initiation(bot_instance, db)
                    if initiation_payload:
                        platform = initiation_payload.get("platform")
                        sender_queue = sender_queues.get(f"{platform}_sender_queue")
                        if sender_queue:
                            await sender_queue.put(initiation_payload)
                            print(f"[BRAIN] Topic initiation sent to {platform} sender.")
                            
                            # Update last activity time to prevent immediate re-initiation
                            bot_state["last_activity_time"] = time.time()
                            state_manager.save_bot_state(bot_state)
                        else:
                            print(f"[BRAIN] ERROR: No sender queue found for platform '{platform}' during initiation.")
                    else:
                        print("[BRAIN] Topic initiation returned no payload.")
                except Exception as e:
                    print(f"[BRAIN] ERROR during topic initiation: {e}")
            else:
                remaining_hours = (min_initiate_hours * 3600 - (time.time() - last_activity)) / 3600
                print(f"[BRAIN] Not initiating topic yet. {remaining_hours:.1f} hours remaining until next initiation window.")
            
            continue
            
        except asyncio.CancelledError:
            print(f"[BRAIN-DEBUG] Worker for user {bot_instance.user_id} cancelled.")
            break
        except Exception as e:
            print(f"CRITICAL ERROR in Brain Worker for user {bot_instance.user_id}: {e}")
            await asyncio.sleep(5)