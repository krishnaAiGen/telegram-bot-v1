import time
from datetime import datetime, timezone

class StateManager:
    """
    Manages all persistent state for a SINGLE bot instance using a user-specific
    document in Google Firestore.
    """
    def __init__(self, db, user_id: str, connection_id: str):        
        """
        Initializes the StateManager for a specific user and connection.

        Args:
            db: An initialized Firestore client instance.
            user_id: The unique ID of the customer.
            connection_id: The unique ID for the bot instance (e.g., 'telegram_main').
        """
        if not all([db, user_id, connection_id]):
            raise ValueError("db, user_id, and connection_id are all required.")
        
        # The path is now dynamic and points to the correct user's state document.
        self.state_doc_ref = (
            db.collection("customers")
            .document(user_id)
            .collection("botState")
            .document(connection_id)
        )
        print(f"[STATE_MANAGER] Initialized for user '{user_id}' at path: {self.state_doc_ref.path}")

    def _get_default_state(self) -> dict:
        """
        Returns the default structure for the state document.
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
        Fetches the state document from Firestore.
        If it doesn't exist, it creates it with a default structure.
        """
        try:
            doc = self.state_doc_ref.get()
            if doc.exists:
                return doc.to_dict()
            else:
                print(f"[STATE_MANAGER] State document for {self.state_doc_ref.id} not found. Creating.")
                default_state = self._get_default_state()
                self.state_doc_ref.set(default_state)
                return default_state
        except Exception as e:
            print(f"CRITICAL ERROR loading state from Firestore: {e}")
            return self._get_default_state()

    def _save_state(self, state: dict):
        """Saves the entire state dictionary back to the Firestore document."""
        try:
            self.state_doc_ref.set(state)
        except Exception as e:
            print(f"CRITICAL ERROR saving state to Firestore: {e}")

    def load_bot_state(self) -> dict:
        """Loads just the core bot state portion of the document."""
        full_state = self._load_state()
        return full_state.get("bot_core_state", self._get_default_state()["bot_core_state"])

    def save_bot_state(self, bot_core_state: dict):
        """Saves just the core bot state portion of the document."""
        full_state = self._load_state()
        full_state["bot_core_state"] = bot_core_state
        self._save_state(full_state)

    def get_link_state(self, link: str) -> dict:
        """Gets the state for a specific link."""
        full_state = self._load_state()
        return full_state.get("link_scheduler_state", {}).get(link, {"last_post_time": 0, "post_count": 0})

    def update_link_state(self, link: str):
        """Updates the state for a link after it has been posted."""
        full_state = self._load_state()
        if "link_scheduler_state" not in full_state:
            full_state["link_scheduler_state"] = {}
        link_data = full_state["link_scheduler_state"].get(link, {"last_post_time": 0, "post_count": 0})
        link_data["last_post_time"] = time.time()
        link_data["post_count"] += 1
        full_state["link_scheduler_state"][link] = link_data
        self._save_state(full_state)

    def get_last_persona_info(self) -> dict:
        """Gets the last used persona's name and timestamp."""
        bot_core_state = self.load_bot_state()
        return bot_core_state.get("last_persona_info", {"name": None, "timestamp": 0})

    def update_last_persona_info(self, persona_name: str):
        """Updates the last used persona."""
        bot_core_state = self.load_bot_state()
        bot_core_state["last_persona_info"] = {"name": persona_name, "timestamp": time.time()}
        self.save_bot_state(bot_core_state)

    def has_processed(self, message_id: str) -> bool:
        """Checks if a message ID has already been processed."""
        full_state = self._load_state()
        return str(message_id) in full_state.get("processed_log", {})

    def log_processed(self, message_id: str):
        """Logs a message ID as processed and prunes the log."""
        full_state = self._load_state()
        if "processed_log" not in full_state:
            full_state["processed_log"] = {}
        log = full_state["processed_log"]
        log[str(message_id)] = datetime.now(timezone.utc).isoformat()
        if len(log) > 500:
            sorted_items = sorted(log.items(), key=lambda item: item[1], reverse=True)
            full_state["processed_log"] = dict(sorted_items[:400])
        self._save_state(full_state)

    def log_initiated_topic(self, topic: str):
        """Logs a topic as initiated and prunes the log."""
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
        """Checks if a topic has been recently initiated."""
        full_state = self._load_state()
        return topic.lower() in (t.lower() for t in full_state.get("initiated_topics", {}).keys())