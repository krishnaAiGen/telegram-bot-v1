# src/services/grok_chat.py
import aiohttp
import os
from config.settings import APP_CONFIG

# Load the API key and define the URL
GROK_API_KEY = APP_CONFIG.get("xai_api_key")
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

async def get_grok_response(content: str, model: str = "grok-3-latest") -> str:
    """
    Gets a response from the Grok API using optional live search.
    """
    if not GROK_API_KEY or GROK_API_KEY == "YOUR_GROK_API_KEY_HERE":
        print("[GROK] API key not configured in .env file.")
        return "Error: Grok API key is not configured."

    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that provides concise, factual answers based on the latest available information and used for paraphrasing."
        },
        {
            "role": "user",
            "content": content
        }
    ]

    # Add live search configuration with automatic mode
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.9,
        "search_parameters": {
            "mode": "auto"               # Let Grok decide when to search
        }
    }

    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession() as session:
        try:
            print(f"[GROK] Sending request to model '{model}' with auto search...")
            async with session.post(GROK_API_URL, headers=headers, json=payload, timeout=timeout) as response:
                response.raise_for_status()
                result = await response.json()

                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                else:
                    print(f"Error: 'choices' key not found in Grok response. Full response: {result}")
                    return "Error: Received an invalid response from the data service."

        except Exception as e:
            print(f"CRITICAL ERROR calling Grok API: {e}")
            return f"Error: Could not get a response from the data service. Details: {e}"
