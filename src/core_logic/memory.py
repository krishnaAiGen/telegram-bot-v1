# src/core_logic/memory.py
from mem0 import MemoryClient
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Mem0 client
memory_client = MemoryClient(api_key=os.getenv("MEM0_API_KEY"))

async def handle_memory(query: str, type: str, user_id: str = "telegram_bot") -> str:
    """
    Handle memory operations for the telegram bot.
    
    Args:
        query: The text content to process
        type: Either "query" or "response" 
        user_id: Unique identifier for the user/bot
        
    Returns:
        String of relevant memories (empty if type is "response")
    """
    try:
        if type == "query":
            # Search for relevant memories first
            search_result = memory_client.search(query=query, user_id=user_id, limit=5)
            
            # Handle different response structures
            if isinstance(search_result, list):
                relevant_memories = [entry.get("memory", "") for entry in search_result if isinstance(entry, dict)]
            elif isinstance(search_result, dict) and "results" in search_result:
                relevant_memories = [entry.get("memory", "") for entry in search_result["results"]]
            else:
                relevant_memories = []
            
            # Add the query to memory
            memory_client.add([{"role": "user", "content": query}], user_id=user_id)
            
            # Format relevant memories for prompt
            if relevant_memories:
                memories_str = "\n".join(f"- {m}" for m in relevant_memories if m)
                return f"Previous relevant interactions:\n{memories_str}\n\n"
            else:
                return ""
                
        elif type == "response":
            # Just add the response to memory, don't search
            memory_client.add([{"role": "assistant", "content": query}], user_id=user_id)
            return ""
        else:
            print(f"[MEMORY] Invalid type '{type}'. Must be 'query' or 'response'")
            return ""
            
    except Exception as e:
        print(f"[MEMORY] Error handling memory operation: {e}")
        return ""

def get_memory_context(query: str, user_id: str = "telegram_bot") -> str:
    """
    Get relevant memory context for a query without adding it to memory.
    Useful for getting context before LLM calls.
    """
    try:
        search_result = memory_client.search(query=query, user_id=user_id, limit=5)
        
        # Handle different response structures
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
        print(f"[MEMORY] Error getting memory context: {e}")
        return ""

def add_to_memory(content: str, role: str = "assistant", user_id: str = "telegram_bot"):
    """
    Add content to memory without searching.
    
    Args:
        content: The content to add
        role: Either "user" or "assistant"
        user_id: Unique identifier for the user/bot
    """
    try:
        memory_client.add([{"role": role, "content": content}], user_id=user_id)
        print(f"[MEMORY] Added {role} content to memory")
    except Exception as e:
        print(f"[MEMORY] Error adding to memory: {e}") 