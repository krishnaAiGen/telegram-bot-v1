import asyncio
import datetime
from google.cloud.firestore import Query

def save_message_to_db(collection_name: str, message, db):
    """Saves a Telethon message object to a Firestore collection."""
    if not message or not message.text:
        return
    
    collection_ref = db.collection(f"conversation_ai_{collection_name}")
    doc_ref = collection_ref.document(str(message.id))
    doc_data = {
        "message_id": message.id,
        "text": message.text,
        "sender_id": getattr(message.sender, 'id', None),
        "date": message.date
    }
    doc_ref.set(doc_data)
    print(f"[DB] Saved message ID {message.id} to Firestore.")

def _get_docs_sync(query):
    return [doc.to_dict() for doc in query.stream()]

async def get_last_n_messages_as_text(group_id: str, n: int, db) -> str:
    """Fetches the last N messages and formats them into a simple text block."""
    collection_ref = db.collection(f"conversation_ai_{group_id}")
    query = collection_ref.order_by("date", direction=Query.DESCENDING).limit(n)
    docs = await asyncio.to_thread(_get_docs_sync, query)
    
    if not docs:
        return "No recent messages."
        
    # chronological order
    docs.reverse()
    
    formatted_history = []
    for doc in docs:
        # In a real scenario, you might fetch user names, but for the LLM, this is enough
        sender = doc.get('sender_id', 'User')
        text = doc.get('text', '')
        formatted_history.append(f"User {sender}: {text}")
        
    return "\n".join(formatted_history)

async def get_last_100_message_texts(collection_name: str, db) -> list[str]:
    collection_ref = db.collection(f"conversation_ai_{collection_name}")
    query = collection_ref.order_by("date", direction=Query.DESCENDING).limit(100)
    docs = await asyncio.to_thread(_get_docs_sync, query)
    return [doc.get('text', '') for doc in docs if 'text' in doc]