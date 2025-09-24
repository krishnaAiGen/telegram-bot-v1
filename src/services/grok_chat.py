# src/services/grok_chat.py
import aiohttp

GROK_API_URL = "https://api.x.ai/v1/chat/completions"

async def get_grok_response(content: str, grok_api_key: str, model: str = "grok-3-latest") -> str:
    """
    Gets a response from the Grok API using a provided API key.
    """
    if not grok_api_key:
        return "Error: Grok API key was not provided."

    headers = {
        "Authorization": f"Bearer {grok_api_key}",
        "Content-Type": "application/json",
    }

    messages = [{"role": "user", "content": content}]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7, # Adjusted for more creative but still factual responses
        "search_parameters": {"mode": "auto"}
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
                    return "Error: Received an invalid response from the data service."
        except Exception as e:
            print(f"CRITICAL ERROR calling Grok API: {e}")
            return f"Error: Could not get a response from the data service. Details: {e}"