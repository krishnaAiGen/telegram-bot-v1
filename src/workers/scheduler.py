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

# Path to the links schedule
LINKS_SCHEDULE_PATH = os.path.join('config', 'links.json')

async def scheduler_worker(sender_queue: asyncio.Queue, persona_manager: PersonaManager, state_manager: StateManager, db):
    """A background worker that checks a schedule and posts links intelligently."""
    print("[SCHEDULER] Worker started.")
    
    # A local queue for links that are due to be posted
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

        # 2. Check and Queue Due Links
        for link_info in schedule:
            link = link_info.get("link")
            interval = link_info.get("time_interval")
            last_posted = state_manager.get_link_last_post_time(link)
            
            is_due = False
            if isinstance(interval, int):
                # Apply "jitter" of +/- 10% to the interval
                jitter = interval * 0.10
                jittered_interval_seconds = (interval + random.uniform(-jitter, jitter)) * 60
                if now - last_posted > jittered_interval_seconds:
                    is_due = True
            elif interval == "random":
                # Small chance to post "random" links on any given cycle
                if random.random() < 0.02: # Approx. 2% chance per minute
                    is_due = True
            
            if is_due:
                if link not in [p['link'] for p in pending_links]:
                    print(f"[SCHEDULER] Link '{link}' is due. Adding to pending queue.")
                    pending_links.append(link_info)
        
        # 3. Process the Pending Queue with Global Cooldown
        if pending_links:
            bot_state = state_manager.load_bot_state()
            global_cooldown_seconds = APP_CONFIG.get("link_post_cooldown_mins", 15) * 60
            
            if now - bot_state.get("global_last_link_post_time", 0) > global_cooldown_seconds:
                print("[SCHEDULER] Global cooldown has passed. Processing one link from pending queue.")
                
                link_to_post = pending_links.popleft()
                
                # Get the crafted message from our intelligent handler
                message_to_send = await handle_scheduled_link_post(link_to_post, persona_manager, db)
                
                if message_to_send:
                    await sender_queue.put(message_to_send)
                    print(f"[SCHEDULER] Sent '{link_to_post['link']}' to sender queue.")
                    
                    # Update timers
                    state_manager.update_link_last_post_time(link_to_post['link'])
                    bot_state["global_last_link_post_time"] = time.time()
                    state_manager.save_bot_state(bot_state)
                else:
                    print(f"[SCHEDULER] Failed to generate message for '{link_to_post['link']}'. Will retry later.")
            else:
                print(f"[SCHEDULER] In global cooldown. {len(pending_links)} links are waiting in the queue.")