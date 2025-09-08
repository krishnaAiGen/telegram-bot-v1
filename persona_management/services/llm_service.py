# persona_management/services/llm_service.py

import json
from openai import AsyncOpenAI
from typing import Any, Dict

# This service is now fully stateless. It does not load any config.
LLM_MODEL_NAME = "gpt-4-turbo-preview"

async def generate_text_response(prompt: str, openai_api_key: str) -> str:
    """
    Generates a simple text response using a provided OpenAI API key.
    """
    if not openai_api_key:
        raise ValueError("OpenAI API key is required for LLM service.")
    
    # Client is created on-demand with the user's key
    client = AsyncOpenAI(api_key=openai_api_key)
    
    try:
        print(f"--- Sending text prompt to {LLM_MODEL_NAME} ---")
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
            raise ValueError("LLM returned an empty response.")
        print("--- Received text response from LLM ---")
        return content.strip()
    except Exception as e:
        print(f"CRITICAL ERROR in LLM text generation: {e}")
        raise # Re-raise the exception to be handled by the agent

async def generate_json_response(prompt: str, openai_api_key: str) -> Dict[str, Any]:
    """
    Generates a structured JSON response using a provided OpenAI API key.
    """
    if not openai_api_key:
        raise ValueError("OpenAI API key is required for LLM service.")

    # Client is created on-demand with the user's key
    client = AsyncOpenAI(api_key=openai_api_key)

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
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty JSON response.")
        
        print("--- Received and parsed JSON response from LLM ---")
        return json.loads(content)
    except Exception as e:
        print(f"CRITICAL ERROR in LLM JSON generation: {e}")
        # Re-raise the exception to allow the calling agent to handle the failure
        raise