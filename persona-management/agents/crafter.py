# persona-management/agents/crafter.py

from typing import List
from ..schemas.pipeline_state import PipelineState
from ..schemas.persona_profile import PersonaProfile
from ..services.llm_service import generate_json_response
import asyncio

CRAFTER_PROMPT_TEMPLATE = """
You are a master AI Persona Crafter. Your job is to take a high-level persona role and description and expand it into a detailed, ready-to-use persona profile.

The persona's designated role is: "{role}"
The description of its function is: "{description}"

Based on this, generate a complete persona profile. The persona should be creative, coherent, and perfectly suited for its role. Your output MUST be a single, valid JSON object that strictly follows this structure:
{{
  "persona_name": "A creative and fitting name for the persona",
  "tagline": "A short, catchy tagline that captures its essence",
  "role": "The designated role provided above",
  "expertise": ["A list of 3-5 specific areas of expertise relevant to the role"],
  "signature_voice": {{
    "tone": "Describe the tone in 3-5 adjectives (e.g., witty, formal, enthusiastic)",
    "style": "Describe the communication style (e.g., uses short sentences, asks questions)",
    "language_habits": ["A list of 2-3 specific language patterns (e.g., uses specific slang, avoids jargon)"]
  }},
  "allow_emojis": "A boolean value (true or false) indicating if it uses emojis",
  "key_traits": ["A list of 3-5 core personality traits"],
  "knowledge_boundaries": {{
    "will_defer_on": ["A list of topics this persona should avoid and defer to others"],
    "refusal_message": "A polite but in-character message to use when it cannot answer a question"
  }},
  "examples": [
    {{
      "user": "A sample user question that this persona would handle",
      "assistant": "A sample response from the persona, showcasing its voice and style"
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

    Args:
        state: The current pipeline state, containing `persona_blueprints`.

    Returns:
        The updated state with `generated_personas` populated.
    """
    print(f"[CrafterAgent] Crafting {len(state.persona_blueprints)} full persona profiles...")

    if not state.persona_blueprints:
        error_message = "CrafterAgent failed: No persona blueprints were provided."
        print(f"ERROR: {error_message}")
        state.status = 'FAILED'
        state.feedback_notes = error_message
        return state
        
    crafted_personas: List[PersonaProfile] = []
    
    # We will run the LLM calls for each blueprint concurrently for speed.
    tasks = []
    for blueprint in state.persona_blueprints:
        prompt = CRAFTER_PROMPT_TEMPLATE.format(
            role=blueprint.role,
            description=blueprint.description
        )
        tasks.append(generate_json_response(prompt))

    # Wait for all the LLM calls to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        blueprint = state.persona_blueprints[i]
        if isinstance(result, Exception) or "error" in result:
            error_message = f"CrafterAgent failed for role '{blueprint.role}': LLM call failed or returned an error. Details: {result}"
            print(f"ERROR: {error_message}")
            state.status = 'FAILED'
            state.feedback_notes = error_message
            return state # Fail the entire pipeline if one craft fails
        
        try:
            # Use Pydantic to parse the entire complex object.
            # This is the ultimate validation step.
            full_profile = PersonaProfile(**result)
            crafted_personas.append(full_profile)
            print(f"  - Successfully crafted persona: '{full_profile.persona_name}'")

        except Exception as e:
            error_message = f"CrafterAgent failed for role '{blueprint.role}': Pydantic validation error. The LLM output did not match the required schema. Details: {e}"
            print(f"ERROR: {error_message}")
            print(f"LLM Response was: {result}")
            state.status = 'FAILED'
            state.feedback_notes = error_message
            return state

    state.generated_personas = crafted_personas
    # The next step after crafting is to check against memory for duplicates.
    state.status = 'CHECKING_MEMORY'
    
    print(f"[CrafterAgent] Successfully crafted all {len(crafted_personas)} persona profiles.")
    return state