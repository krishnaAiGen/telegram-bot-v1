# persona-management/services/llm_service.py

import json
from openai import AsyncOpenAI
from typing import Any, Dict, List
import sys
import os

# It adds the parent directory ('telegram-bot-v1') to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from config.settings import APP_CONFIG

# --- Initialize the OpenAI Client ---

# We only need the OpenAI key for this module
if not APP_CONFIG.get("openai_api_key"):
    raise ValueError("CRITICAL: OPENAI_API_KEY is not found in the main .env file.")

# Create a single, reusable async client instance
client = AsyncOpenAI(api_key=APP_CONFIG["openai_api_key"])
LLM_MODEL_NAME = "gpt-4-turbo-preview" # You can move this to a config later if you wish

async def generate_text_response(prompt: str) -> str:
    """
    Generates a simple text response from a given prompt.

    Args:
        prompt: The user-facing or system prompt.

    Returns:
        The text content of the AI's response.
    """
    try:
        print(f"--- Sending prompt to {LLM_MODEL_NAME} ---")
        # For simple text, you can use a basic chat completion
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Received an empty response from the LLM.")
        print("--- Received text response from LLM ---")
        return content.strip()

    except Exception as e:
        print(f"ERROR: Failed to get text response from LLM: {e}")
        # In a real app, you might want to return None or raise the exception
        return f"Error: Could not process the request. Details: {e}"

async def generate_json_response(prompt: str) -> Dict[str, Any]:
    """
    Generates a response from the LLM and forces it to be valid JSON.

    This is the primary function our agents will use.

    Args:
        prompt: The system prompt instructing the AI to generate JSON.

    Returns:
        A dictionary parsed from the AI's JSON response.
        Returns an empty dictionary on failure.
    """
    try:
        print(f"--- Sending JSON prompt to {LLM_MODEL_NAME} ---")
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant designed to output JSON. Respond ONLY with valid JSON based on the user's request."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}, # This is the key feature for reliable JSON
            temperature=0.3, # Lower temperature for more predictable, structured output
        )
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Received an empty JSON response from the LLM.")
        
        print("--- Received and parsed JSON response from LLM ---")
        # The content should be a valid JSON string, so we parse it
        return json.loads(content)

    except json.JSONDecodeError as e:
        print(f"ERROR: LLM returned invalid JSON. Content: '{content}'. Error: {e}")
        return {"error": "LLM returned invalid JSON", "content": content}
    except Exception as e:
        print(f"ERROR: Failed to get JSON response from LLM: {e}")
        return {"error": f"Failed to get JSON response from LLM: {e}"}