# src/workers/scheduler.py
import asyncio
import time
import json
import os
import random
from collections import deque
from asyncio import Queue


from config.settings import APP_CONFIG
from src.services.state_manager import StateManager
from src.core_logic.llm_personas import PersonaManager
from src.core_logic.response_logic import handle_scheduled_link_post

LINKS_SCHEDULE_PATH = os.path.join('config', 'links.json')

async def scheduler_worker(sender_queues: dict[str, Queue], persona_manager: PersonaManager, state_manager: StateManager, db):
    """A background worker that checks a schedule and posts links based on advanced strategies."""
    print("[SCHEDULER] Worker started.")
    pending_links = deque()
    LINKS_SCHEDULE_PATH = os.path.join('config', 'links.json')

    while True:
        # Check the schedule at regular intervals (e.g., every 60 seconds)
        await asyncio.sleep(60)

        # 1. Dynamically reload the schedule from the JSON file each cycle
        try:
            with open(LINKS_SCHEDULE_PATH, 'r', encoding='utf-8') as f:
                schedule = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[SCHEDULER] ERROR: Could not load or parse links.json: {e}. Retrying next cycle.")
            continue

        print(f"[SCHEDULER] Checking schedule with {len(schedule)} links...")
        now = time.time()

        # 2. Check each link in the schedule to see if it's due
        for link_info in schedule:
            link = link_info.get("link")
            strategy = link_info.get("posting_strategy")
            interval_mins = link_info.get("time_interval")
            
            # Skip if essential info is missing
            if not all([link, strategy, interval_mins]):
                continue

            link_state = state_manager.get_link_state(link)
            last_posted = link_state.get("last_post_time", 0)
            post_count = link_state.get("post_count", 0)
            
            is_due = False
            
            # --- Advanced Strategy Logic ---
            if strategy == "once" and post_count == 0:
                is_due = True
            elif isinstance(strategy, int) and post_count < strategy:
                if post_count == 0 or (now - last_posted > interval_mins * 60):
                    is_due = True
            elif strategy == "recurrent":
                # Apply "jitter" to the interval to make posts less predictable
                jitter = interval_mins * 0.10
                jittered_interval_seconds = (interval_mins + random.uniform(-jitter, jitter)) * 60
                if now - last_posted > jittered_interval_seconds:
                    is_due = True
            
            # If a link is due and not already in the pending queue, add it
            if is_due:
                # Check against the link URL to prevent duplicates in the pending queue
                if link not in [p.get('link') for p in pending_links]:
                    print(f"[SCHEDULER] Link '{link}' is due (Strategy: {strategy}). Adding to pending queue.")
                    pending_links.append(link_info)
        
        # 3. Process one item from the pending queue if the global cooldown has passed
        if pending_links:
            bot_state = state_manager.load_bot_state()
            cooldown_seconds = APP_CONFIG.get("link_post_cooldown_mins", 15) * 60
            
            if now - bot_state.get("global_last_link_post_time", 0) > cooldown_seconds:
                print("[SCHEDULER] Global cooldown passed. Processing one link from queue.")
                
                # Get the next link to post from the left of the queue
                link_to_post = pending_links.popleft()
                
                try:
                    # --- CORRECTED LOGIC ---
                    # The handler function now does the heavy lifting of crafting the message
                    # and putting it on the correct queue.
                    # We await it directly. It will print its own success/failure messages.
                    await handle_scheduled_link_post(link_to_post, sender_queues, persona_manager, db)
                    
                    # If the handler executes without raising an exception, we consider it a success.
                    # Now we update the state.
                    print(f"[SCHEDULER] Successfully processed and queued message for '{link_to_post['link']}'.")
                    
                    # Update timers for both the specific link and the global cooldown
                    state_manager.update_link_state(link_to_post['link'])
                    bot_state["global_last_link_post_time"] = time.time()
                    state_manager.save_bot_state(bot_state)

                except Exception as e:
                    # Catch any unexpected errors from the handler
                    print(f"[SCHEDULER] CRITICAL ERROR while handling link post for '{link_to_post.get('link')}': {e}")
            
            else:
                # If we are still in the global cooldown period
                wait_time = (bot_state.get("global_last_link_post_time", 0) + cooldown_seconds) - now
                print(f"[SCHEDULER] In global cooldown. {len(pending_links)} links are waiting. Next post possible in {int(wait_time)}s.")