# src/services/state_manager.py
import json
import os
import time
from datetime import datetime, timezone

from config.settings import APP_CONFIG

class StateManager:
    """Manages all persistent file-based state for the application."""
    def __init__(self):
        self.data_dir = APP_CONFIG['data_dir']
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.processed_log_file = os.path.join(self.data_dir, 'processed_log.json')
        self.initiated_topics_file = os.path.join(self.data_dir, 'initiated_topics.json')
        self.bot_state_file = os.path.join(self.data_dir, 'bot_state.json')
        self.link_scheduler_state_file = os.path.join(self.data_dir, 'link_scheduler_state.json')

        
        self.save_json(self.processed_log_file, {}) 
        self.save_json(self.initiated_topics_file, {})
        # Initialize bot state with defaults if the file doesn't exist
        self._init_json_file(self.bot_state_file, {
            "last_activity_time": time.time(),
            "last_persona_info": {"name": None, "timestamp": 0},
            "global_last_link_post_time": 0
        })
        self._init_json_file(self.link_scheduler_state_file, {})

    def _init_json_file(self, file_path, default_content):
        if not os.path.exists(file_path):
            self.save_json(file_path, default_content)

    def load_json(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            # Return a default structure if file is corrupt or not found
            if 'log' in file_path or 'topics' in file_path:
                return {}
            if 'state' in file_path:
                return {"last_activity_time": time.time(), "last_persona_info": {"name": None, "timestamp": 0}}
            return {}

    def save_json(self, file_path, data):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    # --- Methods for Core Bot State ---
    def load_bot_state(self) -> dict:
        state = self.load_json(self.bot_state_file)
        # Ensure default keys exist if file was empty or corrupted
        state.setdefault("last_activity_time", time.time())
        state.setdefault("last_persona_info", {"name": None, "timestamp": 0})
        state.setdefault("global_last_link_post_time", 0)
        return state

    def save_bot_state(self, state: dict):
        self.save_json(self.bot_state_file, state)
        
    def get_link_last_post_time(self, link: str) -> float:
        """Gets the timestamp of when a specific link was last posted."""
        link_state = self.load_json(self.link_scheduler_state_file)
        return link_state.get(link, 0)

    def update_link_last_post_time(self, link: str):
        """Updates the timestamp for a specific link to the current time."""
        link_state = self.load_json(self.link_scheduler_state_file)
        link_state[link] = time.time()
        self.save_json(self.link_scheduler_state_file, link_state)


    # --- NEW: Methods specifically for Persona Stickiness ---
    def get_last_persona_info(self) -> dict:
        """Safely gets the last used persona's info from the state file."""
        state = self.load_bot_state()
        return state.get("last_persona_info", {"name": None, "timestamp": 0})

    def update_last_persona_info(self, persona_name: str):
        """Updates the state file with the latest persona used."""
        state = self.load_bot_state()
        state["last_persona_info"] = {"name": persona_name, "timestamp": time.time()}
        self.save_bot_state(state)

    # --- Methods for Message and Topic Logs ---
    def has_processed(self, message_id: int) -> bool:
        log = self.load_json(self.processed_log_file)
        return str(message_id) in log

    def log_processed(self, message_id: int):
        log = self.load_json(self.processed_log_file)
        log[str(message_id)] = datetime.now(timezone.utc).isoformat()
        if len(log) > 500:
            log = dict(list(log.items())[-400:])
        self.save_json(self.processed_log_file, log)

    def log_initiated_topic(self, topic: str):
        topics = self.load_json(self.initiated_topics_file)
        topics[topic] = datetime.now(timezone.utc).isoformat()
        if len(topics) > 50:
            topics = dict(list(topics.items())[-40:])
        self.save_json(self.initiated_topics_file, topics)

    def is_topic_recently_initiated(self, topic: str) -> bool:
        topics = self.load_json(self.initiated_topics_file)
        return topic.lower() in (t.lower() for t in topics.keys())