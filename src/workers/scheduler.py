# src/workers/scheduler.py
import asyncio
import time
import random
from collections import deque
from asyncio import Queue

# Stateless tools
from src.core_logic.response_logic import handle_scheduled_link_post

# Core data structures
from src.bot_instance import BotInstance

async def scheduler_worker(sender_queues: dict[str, Queue], bot_instance: BotInstance, db: any):
    """
    A background worker that checks a user-specific schedule and posts links.
    """
    print(f"[SCHEDULER] Worker started for user: {bot_instance.user_id}")
    
    pending_links = deque()
    state_manager = bot_instance.state_manager # Get the user's state manager

    while True:
        # Check the schedule at regular intervals (e.g., every 60 seconds)
        await asyncio.sleep(60)

        # 1. Get the user-specific schedule from the BotInstance
        schedule = bot_instance.behavior_settings.get("links_schedule", [])
        if not schedule:
            # If user has no links configured, we can sleep longer to save resources
            await asyncio.sleep(300) 
            continue

        print(f"[SCHEDULER] Checking schedule with {len(schedule)} links for user {bot_instance.user_id}...")
        now = time.time()

        # 2. Check each link in the schedule to see if it's due
        for link_info in schedule:
            link = link_info.get("link")
            strategy = link_info.get("posting_strategy")
            interval_mins = link_info.get("time_interval")
            
            if not all([link, strategy, interval_mins]):
                continue

            link_state = state_manager.get_link_state(link)
            last_posted = link_state.get("last_post_time", 0)
            post_count = link_state.get("post_count", 0)
            
            is_due = False
            
            if strategy == "once" and post_count == 0:
                is_due = True
            elif isinstance(strategy, int) and post_count < strategy:
                if now - last_posted > interval_mins * 60:
                    is_due = True
            elif strategy == "recurrent":
                jitter = interval_mins * 0.10
                jittered_interval_seconds = (interval_mins + random.uniform(-jitter, jitter)) * 60
                if now - last_posted > jittered_interval_seconds:
                    is_due = True
            
            if is_due:
                if link not in [p.get('link') for p in pending_links]:
                    print(f"[SCHEDULER] Link '{link}' is due for user {bot_instance.user_id}. Adding to queue.")
                    pending_links.append(link_info)
        
        # 3. Process one item from the pending queue if the global cooldown has passed
        if pending_links:
            bot_state = state_manager.load_bot_state()
            cooldown_mins = bot_instance.behavior_settings.get("link_post_cooldown_mins", 15)
            cooldown_seconds = cooldown_mins * 60
            
            if now - bot_state.get("global_last_link_post_time", 0) > cooldown_seconds:
                print(f"[SCHEDULER] Cooldown passed for user {bot_instance.user_id}. Processing one link.")
                
                link_to_post = pending_links.popleft()
                
                try:
                    # The handler function returns a payload dictionary or None
                    payload = await handle_scheduled_link_post(link_to_post, bot_instance, db)
                    
                    if payload:
                        platform = payload.get("platform")
                        sender_queue = sender_queues.get(f"{platform}_sender_queue")
                        if sender_queue:
                            await sender_queue.put(payload)
                            print(f"[SCHEDULER] Dispatched link post for user {bot_instance.user_id} to {platform} sender.")
                            
                            # On success, update the state
                            state_manager.update_link_state(link_to_post['link'])
                            bot_state["global_last_link_post_time"] = time.time()
                            state_manager.save_bot_state(bot_state)
                        else:
                            print(f"[SCHEDULER] ERROR: No sender queue found for platform '{platform}' for user {bot_instance.user_id}.")
                    else:
                        print(f"[SCHEDULER] Link post handler returned no payload for user {bot_instance.user_id}.")

                except Exception as e:
                    print(f"[SCHEDULER] CRITICAL ERROR while handling link post for user {bot_instance.user_id}: {e}")
            
            else:
                wait_time = (bot_state.get("global_last_link_post_time", 0) + cooldown_seconds) - now
                print(f"[SCHEDULER] In cooldown for user {bot_instance.user_id}. {len(pending_links)} links waiting. Next post in {int(wait_time)}s.")