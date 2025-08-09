# src/core_logic/memory.py
from mem0 import MemoryClient
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Mem0 client
memory_client = MemoryClient(api_key=os.getenv("MEM0_API_KEY"))

def _generate_user_id(platform: str, user_id: str) -> str:
    """Creates a unique, composite user ID for mem0, e.g., 'telegram_12345'."""
    return f"{platform}_{user_id}"

# MODIFIED: Now accepts platform and user_id, replacing the old hardcoded user_id
def get_memory_context(query: str, platform: str, user_id: str) -> str:
    """
    Get relevant memory context for a query without adding it to memory.
    Now uses a platform-specific user ID.
    """
    # Create the dynamic ID for this specific user on this specific platform
    mem0_user_id = _generate_user_id(platform, user_id)
    
    try:
        search_result = memory_client.search(query=query, user_id=mem0_user_id, limit=5)
        
        # Your original logic for handling the response structure is kept
        if isinstance(search_result, list):
            relevant_memories = [entry.get("memory", "") for entry in search_result if isinstance(entry, dict)]
        elif isinstance(search_result, dict) and "results" in search_result:
            relevant_memories = [entry.get("memory", "") for entry in search_result["results"]]
        else:
            relevant_memories = []
        
        if relevant_memories:
            memories_str = "\n".join(f"- {m}" for m in relevant_memories if m)
            return f"Previous relevant interactions:\n{memories_str}\n\n"
        else:
            return ""
            
    except Exception as e:
        print(f"[MEMORY] Error getting memory context for '{mem0_user_id}': {e}")
        return ""

# MODIFIED: Now accepts platform and user_id, replacing the old hardcoded user_id
def add_to_memory(content: str, role: str, platform: str, user_id: str):
    """
    Add content to memory without searching, using a platform-specific ID.
    
    Args:
        content: The content to add
        role: Either "user" or "assistant"
        platform: The originating platform (e.g., 'telegram', 'slack')
        user_id: The user's ID on that platform
    """
    # Create the dynamic ID for this specific user on this specific platform
    mem0_user_id = _generate_user_id(platform, user_id)
    
    try:
        memory_client.add([{"role": role, "content": content}], user_id=mem0_user_id)
        print(f"[MEMORY] Added {role} content to memory for '{mem0_user_id}'")
    except Exception as e:
        print(f"[MEMORY] Error adding to memory for '{mem0_user_id}': {e}")