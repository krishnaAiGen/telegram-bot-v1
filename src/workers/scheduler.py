# src/workers/scheduler.py
import asyncio
import time
import json
import os
import random
from collections import deque

from config.settings import APP_CONFIG
from src.services.state_manager import StateManager
from src.core_logic.llm_personas import PersonaManager
from src.core_logic.response_logic import handle_scheduled_link_post

LINKS_SCHEDULE_PATH = os.path.join('config', 'links.json')

async def scheduler_worker(sender_queue: asyncio.Queue, persona_manager: PersonaManager, state_manager: StateManager, db):
    """A background worker that checks a schedule and posts links based on advanced strategies."""
    print("[SCHEDULER] Worker started.")
    pending_links = deque()

    while True:
        await asyncio.sleep(60) # Check the schedule every 60 seconds

        # 1. Dynamic Schedule Reloading
        try:
            with open(LINKS_SCHEDULE_PATH, 'r', encoding='utf-8') as f:
                schedule = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[SCHEDULER] ERROR: Could not load or parse links.json: {e}. Retrying next cycle.")
            continue

        print(f"[SCHEDULER] Checking schedule with {len(schedule)} links...")
        now = time.time()

        # 2. Check and Queue Due Links based on Strategy
        for link_info in schedule:
            link = link_info.get("link")
            strategy = link_info.get("posting_strategy")
            interval_mins = link_info.get("time_interval")
            
            link_state = state_manager.get_link_state(link)
            last_posted = link_state.get("last_post_time", 0)
            post_count = link_state.get("post_count", 0)
            
            is_due = False
            
            # --- NEW STRATEGY LOGIC ---
            if strategy == "once":
                if post_count == 0:
                    is_due = True
            elif isinstance(strategy, int): # e.g., strategy is 3
                if post_count < strategy:
                    # Check time interval for subsequent posts
                    if post_count == 0 or (now - last_posted > interval_mins * 60):
                        is_due = True
            elif strategy == "recurrent":
                # Apply "jitter" to the interval
                jitter = interval_mins * 0.10
                jittered_interval_seconds = (interval_mins + random.uniform(-jitter, jitter)) * 60
                if now - last_posted > jittered_interval_seconds:
                    is_due = True
            
            if is_due:
                if link not in [p['link'] for p in pending_links]:
                    print(f"[SCHEDULER] Link '{link}' is due (Strategy: {strategy}). Adding to pending queue.")
                    pending_links.append(link_info)
        
        # 3. Process the Pending Queue with Global Cooldown
        if pending_links:
            bot_state = state_manager.load_bot_state()
            cooldown_seconds = APP_CONFIG.get("link_post_cooldown_mins", 15) * 60
            
            if now - bot_state.get("global_last_link_post_time", 0) > cooldown_seconds:
                print("[SCHEDULER] Global cooldown passed. Processing one link from queue.")
                
                link_to_post = pending_links.popleft()
                
                message_to_send = await handle_scheduled_link_post(link_to_post, persona_manager, db)
                
                if message_to_send:
                    await sender_queue.put(message_to_send)
                    print(f"[SCHEDULER] Sent '{link_to_post['link']}' to sender queue.")
                    
                    # Update timers for both the specific link and the global cooldown
                    state_manager.update_link_state(link_to_post['link'])
                    bot_state["global_last_link_post_time"] = time.time()
                    state_manager.save_bot_state(bot_state)
                else:
                    print(f"[SCHEDULER] Failed to generate message for '{link_to_post['link']}'.")
            else:
                print(f"[SCHEDULER] In global cooldown. {len(pending_links)} links are waiting.")