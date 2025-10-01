from typing import List
from ..schemas.pipeline_state import PipelineState
from ..schemas.persona_profile import Persona
from ..services.llm_service import generate_json_response
import asyncio
from pydantic import ValidationError

CRAFTER_PROMPT_TEMPLATE = """
You are a master AI Persona Crafter. Your job is to take a high-level persona role and expand it into a detailed, ready-to-use profile.

Crucially, you must ensure the persona is perfectly aligned with the team's overall mission and its place within the team structure.

**Overall Mission:** "{user_goal}"
**Team Charter & Context:** "{team_context}"

Your specific task is to craft the persona for the role of **"{role}"** with the function: **"{description}"**.

Based on ALL of the information above, generate a complete persona profile. The persona should be creative, coherent, and perfectly suited for its role *within this specific team and for this specific mission*. Its expertise and examples should be highly relevant to the mission.

Your output MUST be a single, valid JSON object that strictly follows this structure:
{{
  "persona_name": "A creative name, relevant to the mission",
  "tagline": "A catchy tagline that captures its essence",
  "role": "{role}",
  "expertise": ["A list of 3-5 specific areas of expertise highly relevant to the overall mission"],
  "signature_voice": {{
    "tone": "Describe a tone that complements the other team members described in the charter",
    "style": "Describe the communication style",
    "language_habits": ["A list of 2-3 specific language patterns"]
  }},
  "allow_emojis": true,
  "key_traits": ["A list of 3-5 core personality traits"],
  "knowledge_boundaries": {{
    "will_defer_on": ["Topics this persona should avoid, possibly deferring to a teammate"],
    "refusal_message": "A polite, in-character refusal message"
  }},
  "examples": [
    {{
      "user": "A sample user question reflecting the overall mission",
      "assistant": "A sample response showcasing the persona's unique voice and expertise"
    }},
    {{
      "user": "Another sample user question",
      "assistant": "Another sample response"
    }}
  ]
}}
"""

async def run_crafter_agent(state: PipelineState) -> PipelineState:
    """
    Executes the Crafter agent to expand persona blueprints into full profiles.
    This version includes retry logic for individual blueprint crafting failures.
    """
    print(f"[CrafterAgent] Crafting {len(state.persona_blueprints)} full persona profiles...")

    if not state.persona_blueprints:
        error_message = "CrafterAgent failed: No persona blueprints were provided."
        print(f"ERROR: {error_message}")
        state.status = 'FAILED'
        state.feedback_notes = error_message
        return state
        
    crafted_personas: List[Persona] = []
    
    # We will process blueprints one by one to handle individual retries.
    for i, blueprint in enumerate(state.persona_blueprints):
        print(f"  - [{(i+1)}/{len(state.persona_blueprints)}] Crafting role: '{blueprint.role}'...")
        max_retries = 2
        for attempt in range(max_retries):
            try:
                prompt = CRAFTER_PROMPT_TEMPLATE.format(
                    user_goal=state.initial_prompt,
                    team_context=state.team_charter,
                    role=blueprint.role,
                    description=blueprint.description
                )
                
                llm_response = await generate_json_response(
                    prompt=prompt,
                    openai_api_key=state.openai_api_key,
                    # NEW: Add this line for a unique ID per persona
                    call_identifier=f"crafter_agent_role_{blueprint.role}" 
                )

                # The critical validation step is now inside a try block
                full_profile = Persona(**llm_response)
                crafted_personas.append(full_profile)
                print(f"    - Success: Crafted persona '{full_profile.persona_name}' on attempt {attempt + 1}.")
                break # Exit the retry loop on success

            except ValidationError as e:
                # This is the specific error we encountered!
                print(f"    - WARNING: Pydantic validation failed on attempt {attempt + 1} for role '{blueprint.role}'.")
                if attempt < max_retries - 1:
                    print(f"    - Retrying...")
                else:
                    # If all retries fail, then we fail the entire pipeline
                    error_message = f"CrafterAgent failed for role '{blueprint.role}' after {max_retries} attempts due to a persistent Pydantic validation error. Details: {e}"
                    print(f"ERROR: {error_message}")
                    print(f"Last failing LLM Response was: {llm_response}")
                    state.status = 'FAILED'
                    state.feedback_notes = error_message
                    return state
            
            except Exception as e:
                # Catch other potential errors (network, etc.)
                print(f"    - WARNING: An unexpected error occurred on attempt {attempt + 1} for role '{blueprint.role}': {e}")
                if attempt < max_retries - 1:
                    print(f"    - Retrying...")
                else:
                    error_message = f"CrafterAgent failed for role '{blueprint.role}' after {max_retries} attempts due to an unexpected error. Details: {e}"
                    print(f"ERROR: {error_message}")
                    state.status = 'FAILED'
                    state.feedback_notes = error_message
                    return state

    state.generated_personas = crafted_personas
    state.status = 'CHECKING_MEMORY'
    
    print(f"[CrafterAgent] Successfully crafted all {len(crafted_personas)} persona profiles.")
    return state