# persona_management/services/llm_service.py

import json
from openai import AsyncOpenAI
from typing import Any, Dict
import time      # NEW: Import time
import logging   # NEW: Import logging

# Get the logger we configured in the main script
logger = logging.getLogger("llm_logger")

LLM_MODEL_NAME = "gpt-4-turbo-preview"

async def generate_text_response(prompt: str, openai_api_key: str, call_identifier: str = "unknown_text_call") -> str:
    """
    Generates a simple text response and logs performance and token usage.
    """
    if not openai_api_key:
        raise ValueError("OpenAI API key is required for LLM service.")
    
    client = AsyncOpenAI(api_key=openai_api_key)
    start_time = time.monotonic() # NEW: Start timer
    
    try:
        print(f"--- Sending text prompt to {LLM_MODEL_NAME} for: {call_identifier} ---")
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        
        # --- NEW: Logging Logic ---
        duration_ms = (time.monotonic() - start_time) * 1000
        usage = response.usage
        if usage:
            log_data = {
                "identifier": call_identifier,
                "duration_ms": round(duration_ms),
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "model_name": response.model
            }
            logger.info(log_data)
        # --- END NEW ---
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty response.")
        print("--- Received text response from LLM ---")
        return content.strip()
        
    except Exception as e:
        # --- NEW: Error Logging ---
        duration_ms = (time.monotonic() - start_time) * 1000
        error_log_data = {
            "identifier": call_identifier,
            "duration_ms": round(duration_ms),
            "error": str(e)
        }
        logger.error(error_log_data)
        # --- END NEW ---
        print(f"CRITICAL ERROR in LLM text generation: {e}")
        raise

async def generate_json_response(prompt: str, openai_api_key: str, call_identifier: str = "unknown_json_call") -> Dict[str, Any]:
    """
    Generates a structured JSON response and logs performance and token usage.
    """
    if not openai_api_key:
        raise ValueError("OpenAI API key is required for LLM service.")

    client = AsyncOpenAI(api_key=openai_api_key)
    start_time = time.monotonic() # NEW: Start timer

    try:
        print(f"--- Sending JSON prompt to {LLM_MODEL_NAME} for: {call_identifier} ---")
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

        # --- NEW: Logging Logic ---
        duration_ms = (time.monotonic() - start_time) * 1000
        usage = response.usage
        if usage:
            log_data = {
                "identifier": call_identifier,
                "duration_ms": round(duration_ms),
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "model_name": response.model
            }
            logger.info(log_data)
        # --- END NEW ---
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty JSON response.")
        
        print("--- Received and parsed JSON response from LLM ---")
        return json.loads(content)
        
    except Exception as e:
        # --- NEW: Error Logging ---
        duration_ms = (time.monotonic() - start_time) * 1000
        error_log_data = {
            "identifier": call_identifier,
            "duration_ms": round(duration_ms),
            "error": str(e)
        }
        logger.error(error_log_data)
        # --- END NEW ---
        print(f"CRITICAL ERROR in LLM JSON generation: {e}")
        raise