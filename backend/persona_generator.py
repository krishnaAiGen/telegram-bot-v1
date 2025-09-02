# backend/persona_generator.py
import sys
import os

# Ensure the root directory is in the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 1. We now import the main orchestrator function, not the individual pieces
from persona_management.pipeline import run_persona_factory_pipeline

# 2. We also need to add the openai_api_key to the orchestrator's state
from persona_management.schemas.pipeline_state import PipelineState

async def generate_personas_from_goal(initial_prompt: str, api_key: str) -> list:
    """
    Acts as a simple, secure bridge to the main persona factory pipeline.
    It passes the user's goal and their API key to the powerful orchestrator.
    """
    if not initial_prompt or not api_key:
        raise ValueError("Initial prompt and API key are required.")

    # We need to temporarily set the API key for the orchestrator to use.
    # This is a bit of a workaround because the original orchestrator
    # didn't have multi-tenancy in mind.
    
    # We will modify the PipelineState to accept the api_key.
    # Open `persona_management/schemas/pipeline_state.py` and ensure it has:
    # openai_api_key: str | None = None
    
    # We'll also need to modify the main orchestrator to use it.
    # Open `persona_management/pipeline.py`
    # Change `state = PipelineState(initial_prompt=initial_prompt, status='PLANNING')`
    # to `state = PipelineState(initial_prompt=initial_prompt, status='PLANNING', openai_api_key=api_key)`
    
    print("--- Bridge: Calling the main persona factory pipeline ---")
    
    # This is the key change: we call the "smart manager" directly
    result = await run_persona_factory_pipeline(initial_prompt, api_key=api_key)

    if result.get("status") == "success":
        # The orchestrator now returns a complex dict. We need to extract the personas.
        # It seems to return 'personas' (raw) and 'characters' (formatted).
        # For the draft, the raw 'personas' list is probably best.
        return result.get("personas", [])
    else:
        # If the pipeline failed, raise an error with the reason
        reason = result.get("reason", "Unknown pipeline failure.")
        raise RuntimeError(f"Persona generation pipeline failed: {reason}")