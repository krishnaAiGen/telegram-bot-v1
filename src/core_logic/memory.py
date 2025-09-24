# src/core_logic/memory.py
from mem0 import MemoryClient

def get_memory_client(api_key: str) -> MemoryClient | None:
    """Initializes and returns a MemoryClient with a specific API key."""
    if not api_key:
        print("[MEMORY] Warning: No Mem0 API key provided.")
        return None
    return MemoryClient(api_key=api_key)

def _generate_user_id(platform: str, user_id: str) -> str:
    """Creates a unique, composite user ID for mem0, e.g., 'telegram_12345'."""
    return f"{platform}_{user_id}"

def get_memory_context(query: str, platform: str, user_id: str, mem0_api_key: str) -> str:
    """
    Get relevant memory context for a query using a user-specific API key.
    """
    memory_client = get_memory_client(mem0_api_key)
    if not memory_client:
        return ""

    mem0_user_id = _generate_user_id(platform, user_id)
    
    try:
        search_result = memory_client.search(query=query, user_id=mem0_user_id, limit=5)
        
        relevant_memories = []
        if isinstance(search_result, list):
            relevant_memories = [entry.get("memory", "") for entry in search_result if isinstance(entry, dict)]
        elif isinstance(search_result, dict) and "results" in search_result:
            relevant_memories = [entry.get("memory", "") for entry in search_result["results"]]
        
        if relevant_memories:
            memories_str = "\n".join(f"- {m}" for m in relevant_memories if m)
            return f"Previous relevant interactions:\n{memories_str}\n\n"
        return ""
            
    except Exception as e:
        print(f"[MEMORY] Error getting memory context for '{mem0_user_id}': {e}")
        return ""

def add_to_memory(content: str, role: str, platform: str, user_id: str, mem0_api_key: str):
    """
    Add content to memory using a user-specific API key.
    """
    memory_client = get_memory_client(mem0_api_key)
    if not memory_client:
        return

    mem0_user_id = _generate_user_id(platform, user_id)
    
    try:
        memory_client.add([{"role": role, "content": content}], user_id=mem0_user_id)
        print(f"[MEMORY] Added {role} content to memory for '{mem0_user_id}'")
    except Exception as e:
        print(f"[MEMORY] Error adding to memory for '{mem0_user_id}': {e}")