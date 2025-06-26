# src/workers/brain.py
import asyncio
import time
import random
from config.settings import APP_CONFIG
from src.services.state_manager import StateManager
from src.core_logic.llm_personas import PersonaManager
from src.core_logic.response_logic import handle_reaction, handle_initiation, handle_realtime_query
from src.services.fetch_db import save_message_to_db
from src.services.openai_chat import get_llm_response

async def brain_worker(brain_queue: asyncio.Queue, sender_queue: asyncio.Queue, persona_manager: PersonaManager, state_manager: StateManager, db):
    print("[BRAIN] Worker started.")
    bot_state = state_manager.load_bot_state()
    
    while True:
        try:
            message = await asyncio.wait_for(brain_queue.get(), timeout=1.0)
            
            save_message_to_db(str(APP_CONFIG['telegram_group_id']), message, db)
            
            actual_sender_id = getattr(message.sender, 'id', None)
            if actual_sender_id in APP_CONFIG.get('known_bot_ids', []):
                state_manager.log_processed(message.id)
                brain_queue.task_done()
                continue
            
            if not state_manager.has_processed(message.id):
                # --- STAGE 1: TRIAGE ---
                print(f"[BRAIN] Triage: Analyzing message ID {message.id}...")
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
                print(f"[BRAIN] Triage decision: '{decision}'")

                if "REALTIME_FACTS" in decision:
                    await handle_realtime_query(message, sender_queue, persona_manager, db) 
                else:
                    # --- STAGE 2: PROBABILITY GATE (for persona opinions only) ---
                    response_rate = APP_CONFIG.get("random_response_rate", 1.0)
                    if response_rate < 1.0:
                        roll = random.random()
                        if roll > response_rate:
                            print(f"[BRAIN] Probability gate: Rolled {roll:.2f} > {response_rate}. Choosing not to reply.")
                            # Still log as processed so we don't re-evaluate this message
                            state_manager.log_processed(message.id)
                            brain_queue.task_done()
                            continue
                        else:
                            print(f"[BRAIN] Probability gate: Rolled {roll:.2f} <= {response_rate}. Proceeding with reply.")
                    
                    # If we pass the gate, call the main reaction handler
                    await handle_reaction(message, sender_queue, persona_manager, state_manager, db)

                # Log and update state after any action is taken
                state_manager.log_processed(message.id)
                bot_state["last_activity_time"] = time.time()
                state_manager.save_bot_state(bot_state)
            else:
                 print(f"[BRAIN] Message ID {message.id} has already been processed.")
            brain_queue.task_done()

        except asyncio.TimeoutError:
            now = time.time()
            if now - bot_state['last_activity_time'] > APP_CONFIG['min_initiate_hours'] * 3600:
                await handle_initiation(sender_queue, persona_manager, state_manager, db)
                bot_state["last_activity_time"] = now
                state_manager.save_bot_state(bot_state)
        except Exception as e:
            print(f"CRITICAL ERROR in Brain Worker: {e}")
            await asyncio.sleep(10)