# src/core_logic/internal_message.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class InternalMessage:
    """
    A standardized, internal representation of a message from any platform.
    The core logic of the bot should only ever interact with this object.
    """
    platform: Literal['telegram', 'slack']
    channel_id: str  # For Telegram, this is the group ID. For Slack, the channel ID.
    message_id: str
    text: str
    sender_id: str