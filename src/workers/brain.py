# src/workers/brain.py
import asyncio
import time
import random
from asyncio import Queue 

# Services are now stateless tools
from src.services.fetch_db import save_message_to_db
from src.services.openai_chat import get_llm_response

# The response_logic functions are our primary tools
from src.core_logic.response_logic import handle_reaction, handle_initiation, handle_realtime_query

# Core data structures
from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

async def brain_worker(brain_queue: Queue, sender_queues: dict[str, Queue], bot_instance: BotInstance, db: any):    
    """
    The central processing worker for a SINGLE BotInstance. It consumes from the
    instance's brain_queue and routes responses to the appropriate sender_queues.
    """
    print(f"[BRAIN] Worker started for user: {bot_instance.user_id}")
    
    # Get the user-specific state manager from the instance
    state_manager = bot_instance.state_manager
    bot_state = state_manager.load_bot_state()
    
    while True:
        try:
            message: InternalMessage = await asyncio.wait_for(brain_queue.get(), timeout=1.0)

            # Use the instance's state manager
            if state_manager.has_processed(message.message_id):
                print(f"[BRAIN] Message ID {message.message_id} already processed for user {bot_instance.user_id}. Skipping.")
                brain_queue.task_done()
                continue
            
            # Save message to DB, tagging it with the user ID
            save_message_to_db(message, user_id=bot_instance.user_id, db=db)

            # Get user-specific bot settings from the instance
            known_bot_ids = bot_instance.behavior_settings.get('known_bot_ids', [])
            if message.sender_id in [str(bid) for bid in known_bot_ids]:
                print(f"[BRAIN] Ignoring message from known bot ID {message.sender_id} for user {bot_instance.user_id}")
                state_manager.log_processed(message.message_id)
                brain_queue.task_done()
                continue
            
            # --- STAGE 1: TRIAGE ---
            print(f"[BRAIN] Triage: Analyzing message ID {message.message_id} for user {bot_instance.user_id}...")
            # --- PROMPT PLACEHOLDER ---
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
            
            # # --- END PROMPT PLACEHOLDER ---
            openai_api_key = bot_instance.credentials.get("openai", {}).get("key")
            triage_model = bot_instance.behavior_settings.get("triage_model", "gpt-3.5-turbo")
            if not openai_api_key:
                print(f"CRITICAL: OpenAI key not found for user {bot_instance.user_id} during triage.")
                decision = "PERSONA_OPINION" # Default to a safe category
            else:
                decision = await get_llm_response(triage_prompt, api_key=openai_api_key, model=triage_model, max_tokens=5)
            
            print(f"[BRAIN] Triage decision for user {bot_instance.user_id}: '{decision}'")
            
            response_payload = None # This will hold the dictionary returned by the logic handlers

            if "REALTIME_FACTS" in decision:
                response_payload = await handle_realtime_query(message, bot_instance, db) 
            else:
                response_rate = bot_instance.behavior_settings.get("random_response_rate", 1.0)
                if random.random() < response_rate:
                    print(f"[BRAIN] Probability gate passed for user {bot_instance.user_id}. Generating reaction.")
                    response_payload = await handle_reaction(message, bot_instance, db)
                else:
                    print(f"[BRAIN] Probability gate failed for user {bot_instance.user_id}. Skipping reply.")

            # --- STAGE 2: DISPATCH ---
            if response_payload:
                platform = response_payload.get("platform")
                sender_queue = sender_queues.get(f"{platform}_sender_queue")
                if sender_queue:
                    await sender_queue.put(response_payload)
                    print(f"[BRAIN] Dispatched response payload for user {bot_instance.user_id} to {platform} sender.")
                else:
                    print(f"[BRAIN] ERROR: No sender queue found for platform '{platform}' for user {bot_instance.user_id}.")

            # --- Finalize processing for this message ---
            state_manager.log_processed(message.message_id)
            bot_state["last_activity_time"] = time.time()
            state_manager.save_bot_state(bot_state)
            brain_queue.task_done()

        except asyncio.TimeoutError:
            now = time.time()
            last_activity = bot_state.get('last_activity_time', now)
            min_initiate_hours = bot_instance.behavior_settings.get("min_initiate_hours", 1.0)
            inactivity_period_hours = (now - last_activity) / 3600

            if inactivity_period_hours > min_initiate_hours:
                print(f"[BRAIN] Inactivity of {inactivity_period_hours:.2f} hours detected for user {bot_instance.user_id}. Initiating topic.")
                
                # The logic is now cleaner, just passing the instance
                initiation_payload = await handle_initiation(bot_instance, db)
                
                if initiation_payload:
                    platform = initiation_payload.get("platform")
                    sender_queue = sender_queues.get(f"{platform}_sender_queue")
                    if sender_queue:
                        await sender_queue.put(initiation_payload)
                        print(f"[BRAIN] Dispatched initiation payload for user {bot_instance.user_id} to {platform} sender.")
                
                bot_state["last_activity_time"] = now
                state_manager.save_bot_state(bot_state)

        except Exception as e:
            print(f"CRITICAL ERROR in Brain Worker for user {bot_instance.user_id}: {e}")
            # In a real system, you might want more robust error handling here.
            await asyncio.sleep(5)