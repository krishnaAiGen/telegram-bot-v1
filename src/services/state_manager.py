# src/services/state_manager.py
import json
import os
import time
from datetime import datetime, timezone

from config.settings import APP_CONFIG
# This class no longer needs 'os' or 'json' because it doesn't touch local files.

class StateManager:
    """
    Manages all persistent state for the application using a single document
    in Google Firestore.
    """
    def __init__(self, db):
        """
        Initializes the StateManager with a Firestore database client.

        Args:
            db: An initialized Firestore client instance.
        """
        if db is None:
            raise ValueError("Firestore database client 'db' is required.")
        
        # This is a reference to the specific document that will hold all our state.
        self.state_doc_ref = db.collection("bot_state_prod").document("singleton_state")
        print("[STATE_MANAGER] Initialized with Firestore.")

    def _get_default_state(self) -> dict:
        """
        Returns the default structure for the state document. This is used
        if the document doesn't exist in Firestore yet.
        """
        return {
            "processed_log": {},
            "initiated_topics": {},
            "link_scheduler_state": {},
            "bot_core_state": {
                "last_activity_time": time.time(),
                "last_persona_info": {"name": None, "timestamp": 0},
                "global_last_link_post_time": 0
            }
        }

    def _load_state(self) -> dict:
        """
        Fetches the entire state document from Firestore.
        If the document doesn't exist, it creates it with a default structure.
        """
        try:
            doc = self.state_doc_ref.get()
            if doc.exists:
                # If the document exists, return its data.
                return doc.to_dict()
            else:
                # If it's the very first run, create the document with default values.
                print("[STATE_MANAGER] State document not found. Creating with default values.")
                default_state = self._get_default_state()
                self.state_doc_ref.set(default_state)
                return default_state
        except Exception as e:
            print(f"CRITICAL ERROR loading state from Firestore: {e}")
            # Fallback to a temporary in-memory state if Firestore is unreachable.
            return self._get_default_state()

    def _save_state(self, state: dict):
        """Saves the entire state dictionary back to the Firestore document."""
        try:
            # The 'set' command overwrites the document with the new state.
            self.state_doc_ref.set(state)
        except Exception as e:
            print(f"CRITICAL ERROR saving state to Firestore: {e}")

    # --- Methods for Core Bot State ---
    def load_bot_state(self) -> dict:
        """Loads just the core bot state portion of the document."""
        full_state = self._load_state()
        # Safely get the nested dictionary, providing a default if it's missing.
        return full_state.get("bot_core_state", self._get_default_state()["bot_core_state"])

    def save_bot_state(self, bot_core_state: dict):
        """Saves just the core bot state portion of the document."""
        full_state = self._load_state()
        full_state["bot_core_state"] = bot_core_state
        self._save_state(full_state)

    # --- Methods for Link Scheduler State ---
    def get_link_state(self, link: str) -> dict:
        """
        Gets the state for a specific link (last post time and count).
        Returns a default structure if the link has no state yet.
        """
        full_state = self._load_state()
        return full_state.get("link_scheduler_state", {}).get(link, {"last_post_time": 0, "post_count": 0})

    def update_link_state(self, link: str):
        """
        Updates the state for a link after it has been posted.
        Increments the post count and sets the last post time.
        """
        full_state = self._load_state()
        if "link_scheduler_state" not in full_state:
            full_state["link_scheduler_state"] = {}
        
        # Get current state for the link or create a new one
        link_data = full_state["link_scheduler_state"].get(link, {"last_post_time": 0, "post_count": 0})
        
        # Update the values
        link_data["last_post_time"] = time.time()
        link_data["post_count"] += 1
        
        # Save it back
        full_state["link_scheduler_state"][link] = link_data
        self._save_state(full_state)

    # --- Methods for Persona Stickiness ---
    def get_last_persona_info(self) -> dict:
        bot_core_state = self.load_bot_state()
        return bot_core_state.get("last_persona_info", {"name": None, "timestamp": 0})

    def update_last_persona_info(self, persona_name: str):
        bot_core_state = self.load_bot_state()
        bot_core_state["last_persona_info"] = {"name": persona_name, "timestamp": time.time()}
        self.save_bot_state(bot_core_state)

    # --- Methods for Message and Topic Logs ---
    def has_processed(self, message_id: int) -> bool:
        full_state = self._load_state()
        return str(message_id) in full_state.get("processed_log", {})

    def log_processed(self, message_id: int):
        full_state = self._load_state()
        if "processed_log" not in full_state:
            full_state["processed_log"] = {}
        
        log = full_state["processed_log"]
        log[str(message_id)] = datetime.now(timezone.utc).isoformat()
        
        # Prune the log if it gets too big
        if len(log) > 500:
            # Sort by timestamp and keep the most recent 400
            sorted_items = sorted(log.items(), key=lambda item: item[1], reverse=True)
            full_state["processed_log"] = dict(sorted_items[:400])
        
        self._save_state(full_state)

    def log_initiated_topic(self, topic: str):
        full_state = self._load_state()
        if "initiated_topics" not in full_state:
            full_state["initiated_topics"] = {}
            
        topics = full_state["initiated_topics"]
        topics[topic] = datetime.now(timezone.utc).isoformat()
        
        if len(topics) > 50:
            sorted_items = sorted(topics.items(), key=lambda item: item[1], reverse=True)
            full_state["initiated_topics"] = dict(sorted_items[:40])
            
        self._save_state(full_state)

    def is_topic_recently_initiated(self, topic: str) -> bool:
        full_state = self._load_state()
        return topic.lower() in (t.lower() for t in full_state.get("initiated_topics", {}).keys())