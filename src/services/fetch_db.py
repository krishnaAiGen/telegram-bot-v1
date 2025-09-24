# src/services/fetch_db.py
import asyncio
from google.cloud.firestore import Query
from datetime import datetime, timezone
from src.core_logic.internal_message import InternalMessage

def save_message_to_db(message: InternalMessage, user_id: str, db):
    """Saves a message to a global, scalable log collection, tagged with a user ID."""
    if not message or not message.text:
        return
    
    # Path: /bot_logs/{channel_id}/messages/{message_id}
    doc_ref = (
        db.collection("bot_logs")
        .document(message.channel_id)
        .collection("messages")
        .document(message.message_id)
    )
    
    doc_data = {
        "user_id": user_id,  # Tag the message with the bot owner's ID
        "message_id": message.message_id,
        "text": message.text,
        "sender_id": message.sender_id,
        "platform": message.platform,
        "date": datetime.now(timezone.utc)
    }
    doc_ref.set(doc_data)
    print(f"[DB] Saved message {message.message_id} to log for channel {message.channel_id}.")

async def get_last_n_messages_as_text(channel_id: str, n: int, db) -> str:
    """Fetches the last N messages from the global log for a specific channel."""
    messages_ref = (
        db.collection("bot_logs")
        .document(channel_id)
        .collection("messages")
    )
    query = messages_ref.order_by("date", direction=Query.DESCENDING).limit(n)
    
    def _get_docs_sync(q):
        return [doc.to_dict() for doc in q.stream()]
        
    docs = await asyncio.to_thread(_get_docs_sync, query)
    
    if not docs:
        return "No recent messages."
        
    docs.reverse()
    formatted_history = [f"User {doc.get('sender_id', 'User')}: {doc.get('text', '')}" for doc in docs]
    return "\n".join(formatted_history)

async def get_last_100_message_texts(channel_id: str, db) -> list[str]:
    """Fetches the text of the last 100 messages from the global log for a channel."""
    messages_ref = (
        db.collection("bot_logs")
        .document(channel_id)
        .collection("messages")
    )
    query = messages_ref.order_by("date", direction=Query.DESCENDING).limit(100)
    
    def _get_docs_sync(q):
        results = []
        for doc in q.stream():
            doc_dict = doc.to_dict()
            if doc_dict and 'text' in doc_dict:
                results.append(doc_dict.get('text', ''))
        return results

    docs = await asyncio.to_thread(_get_docs_sync, query)
    return docs