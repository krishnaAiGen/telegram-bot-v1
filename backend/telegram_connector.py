# backend/telegram_connector.py

from telethon import TelegramClient
from typing import Dict

class TelegramConnectionManager:
    """
    Holds temporary, in-memory client objects for users who are in the
    middle of the multi-step Telegram connection process.
    """
    def __init__(self):
        # The key is the user's unique ID (uid), value is the live Telethon client object.
        self.pending_connections: Dict[str, TelegramClient] = {}

    def add_client(self, user_id: str, client: TelegramClient):
        """Stores a new client for a user starting the connection process."""
        self.pending_connections[user_id] = client

    def get_client(self, user_id: str) -> TelegramClient | None:
        """Retrieves a pending client for a user."""
        return self.pending_connections.get(user_id)

    def remove_client(self, user_id: str):
        """Removes a client after the process is complete or has failed."""
        if user_id in self.pending_connections:
            del self.pending_connections[user_id]

# We create a single, global instance of the manager that our API endpoints can share.
# This instance will live as long as the backend server is running.
connection_manager = TelegramConnectionManager()