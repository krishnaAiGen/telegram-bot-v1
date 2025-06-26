import aiohttp
from config.settings import APP_CONFIG

API_KEY = APP_CONFIG.get("openai_api_key")
CHAT_API_URL = "https://api.openai.com/v1/chat/completions"
MODERATION_API_URL = "https://api.openai.com/v1/moderations"

async def get_llm_response(content: str, model: str = "gpt-4", max_tokens: int = 300) -> str:
    if not API_KEY:
        return "Error: OpenAI API key is not configured."

    headers = {"Authorization": f"Bearer {API_KEY}"}
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
        
async def get_embedding(text: str, model="text-embedding-3-small") -> list[float]:
    """Gets a numerical embedding for a given text string."""
    if not API_KEY or not text.strip():
        return []
    
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"input": text, "model": model}
    
    timeout = aiohttp.ClientTimeout(total=30)

    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("https://api.openai.com/v1/embeddings", headers=headers, json=payload, timeout= timeout) as response:
                response.raise_for_status()
                result = await response.json()
                return result["data"][0]["embedding"]
        except Exception as e:
            print(f"Error calling OpenAI Embedding API: {e}")
            return []

async def is_content_offensive(text_to_check: str) -> bool:
    if not text_to_check or not API_KEY:
        return False
        
    headers = {"Authorization": f"Bearer {API_KEY}"}
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