# src/services/openai_chat.py
import aiohttp

CHAT_API_URL = "https://api.openai.com/v1/chat/completions"
EMBEDDINGS_API_URL = "https://api.openai.com/v1/embeddings"
MODERATION_API_URL = "https://api.openai.com/v1/moderations"

async def get_llm_response(content: str, api_key: str, model: str = "gpt-4", max_tokens: int = 300) -> str:
    """Gets a response from the OpenAI Chat API using a provided API key."""
    if not api_key:
        return "Error: OpenAI API key was not provided."

    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens}
    
    timeout = aiohttp.ClientTimeout(total=90) 
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(CHAT_API_URL, headers=headers, json=payload, timeout=timeout) as response:
                response.raise_for_status()
                result = await response.json()
                return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"Error calling OpenAI Chat API: {e}")
            return f"Error: Could not get a response from the language model. Details: {e}"
        
async def get_embedding(text: str, api_key: str, model="text-embedding-3-small") -> list[float]:
    """Gets a numerical embedding using a provided API key."""
    if not api_key or not text.strip():
        return []
    
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"input": text, "model": model}
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(EMBEDDINGS_API_URL, headers=headers, json=payload, timeout=timeout) as response:
                response.raise_for_status()
                result = await response.json()
                return result["data"][0]["embedding"]
        except Exception as e:
            print(f"Error calling OpenAI Embedding API: {e}")
            return []

async def is_content_offensive(text_to_check: str, api_key: str) -> bool:
    """Checks content against the Moderation API using a provided API key."""
    if not text_to_check or not api_key:
        return False
        
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"input": text_to_check}
    
    timeout = aiohttp.ClientTimeout(total=10) 
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(MODERATION_API_URL, headers=headers, json=payload, timeout=timeout) as response:
                response.raise_for_status()
                result = await response.json()
                return result["results"][0]["flagged"]
        except Exception as e:
            print(f"Warning: Moderation API call failed: {e}. Assuming content is safe.")
            return False