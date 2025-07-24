# src/workers/brain.py
import asyncio
import time
import random
from asyncio import Queue 
from config.settings import APP_CONFIG
from src.services.state_manager import StateManager
from src.core_logic.llm_personas import PersonaManager
from src.core_logic.response_logic import handle_reaction, handle_initiation, handle_realtime_query
from src.services.fetch_db import save_message_to_db
from src.services.openai_chat import get_llm_response
from src.core_logic.internal_message import InternalMessage

async def brain_worker(brain_queue: Queue, sender_queues: dict[str, Queue], persona_manager: PersonaManager, state_manager: StateManager, db):    
    """
    The central processing worker. It consumes from a single brain_queue and
    routes responses to the appropriate sender_queues.
    """
    print("[BRAIN] Worker started.")
    bot_state = state_manager.load_bot_state()
    
    while True:
        try:
            # 1. Get a standardized message from the single brain queue
            message: InternalMessage = await asyncio.wait_for(brain_queue.get(), timeout=1.0)

            # 2. Check if the message has already been processed
            if state_manager.has_processed(message.message_id):
                print(f"[BRAIN] Message ID {message.message_id} already processed. Skipping.")
                brain_queue.task_done()
                continue
            
            # 3. Save the new message to the database
            save_message_to_db(message.channel_id, message, db)

            # 4. Check if the message is from a known bot to prevent loops
            # add Slack Bot's User ID to KNOWN_BOT_IDS in .env
            known_bot_ids_str = [str(bid) for bid in APP_CONFIG.get('known_bot_ids', [])]
            if message.sender_id in known_bot_ids_str:
                print(f"[BRAIN] Ignoring message from known bot ID: {message.sender_id}")
                state_manager.log_processed(message.message_id)
                brain_queue.task_done()
                continue
            # --- STAGE 1: TRIAGE ---
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
            decision = await get_llm_response(triage_prompt, model=APP_CONFIG['triage_model'], max_tokens=5)
            print(f"[BRAIN] Triage decision: '{decision}' for message from {message.platform}")

            if "REALTIME_FACTS" in decision:
                print(f"[BRAIN] Routing to handle_realtime_query for message {message.message_id}.")
                await handle_realtime_query(message, sender_queues, persona_manager, db) 
            else:
                response_rate = APP_CONFIG.get("random_response_rate", 1.0)
                if random.random() > response_rate:
                    print(f"[BRAIN] Probability gate: Skipped reply for message {message.message_id} (roll > {response_rate}).")
                    # We do NOT call task_done() or log_processed() here.
                    # We simply do nothing and let the code proceed to the finalization step below.
                else:
                    # If we pass the gate, we proceed with generating a reaction.
                    print(f"[BRAIN] Probability gate: Proceeding with reply for message {message.message_id} (roll <= {response_rate}).")
                    
                    # CORRECT: Pass the 'sender_queues' dictionary
                    await handle_reaction(message, sender_queues, persona_manager, state_manager, db)

            # --- 7. Finalize processing for this message (runs for every message) ---
            # This ensures every message is marked as processed and we don't get stuck.
            
            print(f"[BRAIN] Finalizing processing for message {message.message_id}.")
            
            # Log the message ID to prevent reprocessing
            state_manager.log_processed(message.message_id)
            
            # Update the bot's last activity time
            bot_state["last_activity_time"] = time.time()
            state_manager.save_bot_state(bot_state)
            
            # Signal to the queue that this item is finished
            brain_queue.task_done()


        except asyncio.TimeoutError:
            now = time.time()
            last_activity = bot_state.get('last_activity_time', 0)
            inactivity_period_hours = (now - last_activity) / 3600

            if inactivity_period_hours > APP_CONFIG['min_initiate_hours']:
                print(f"[BRAIN] Inactivity of {inactivity_period_hours:.2f} hours detected. Initiating topic.")
                
                # Defaulting to initiate in Telegram, but this could be made smarter
                telegram_channel_id = str(APP_CONFIG['telegram_group_id'])
                await handle_initiation(
                    'telegram', 
                    telegram_channel_id, 
                    sender_queues, 
                    persona_manager, 
                    state_manager, 
                    db
                )
                
                bot_state["last_activity_time"] = now
                state_manager.save_bot_state(bot_state)

        except Exception as e:
            print(f"CRITICAL ERROR in Brain Worker: {e}")
            await asyncio.sleep(10)