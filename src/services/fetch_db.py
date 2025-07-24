# src/services/fetch_db.py

import asyncio
from google.cloud.firestore import Query
from datetime import datetime, timezone
from src.core_logic.internal_message import InternalMessage

def save_message_to_db(collection_name: str, message: InternalMessage, db):
    """Saves our standardized InternalMessage object to a Firestore collection."""
    if not message or not message.text:
        return
    
    collection_ref = db.collection(f"conversation_ai_{collection_name}")
    doc_ref = collection_ref.document(message.message_id)
    
    doc_data = {
        "message_id": message.message_id,
        "text": message.text,
        "sender_id": message.sender_id,
        "platform": message.platform,
        "date": datetime.now(timezone.utc)
    }
    doc_ref.set(doc_data)
    print(f"[DB] Saved message ID {message.message_id} to Firestore collection for channel {collection_name}.")


async def get_last_n_messages_as_text(group_id: str, n: int, db) -> str:
    """Fetches the last N messages and formats them into a simple text block."""
    collection_ref = db.collection(f"conversation_ai_{group_id}")
    query = collection_ref.order_by("date", direction=Query.DESCENDING).limit(n)
    
    def _get_docs_sync(q):
        # Convert to dictionary immediately
        return [doc.to_dict() for doc in q.stream()]
        
    docs = await asyncio.to_thread(_get_docs_sync, query)
    
    if not docs:
        return "No recent messages."
        
    docs.reverse()
    # Now we are iterating over a list of dictionaries, so .get() is safe
    formatted_history = [f"User {doc.get('sender_id', 'User')}: {doc.get('text', '')}" for doc in docs]
    return "\n".join(formatted_history)


async def get_last_100_message_texts(collection_name: str, db) -> list[str]:
    """Fetches the text of the last 100 messages from a collection."""
    collection_ref = db.collection(f"conversation_ai_{collection_name}")
    query = collection_ref.order_by("date", direction=Query.DESCENDING).limit(100)
    
    def _get_docs_sync(q):
        # --- THIS IS THE FIX ---
        # The list comprehension now correctly converts each doc to a dictionary first
        results = []
        for doc in q.stream():
            doc_dict = doc.to_dict()
            if doc_dict and 'text' in doc_dict:
                results.append(doc_dict.get('text', ''))
        return results

    docs = await asyncio.to_thread(_get_docs_sync, query)
    return docs