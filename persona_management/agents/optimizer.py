# persona-management/agents/optimizer.py

import json
from ..schemas.pipeline_state import PipelineState
from ..schemas.persona_profile import Persona
from ..services.llm_service import generate_json_response

OPTIMIZER_PROMPT_TEMPLATE = """
You are a master AI System Optimizer. Your task is to analyze a list of AI persona profiles and refine it for maximum clarity, distinctiveness, and alignment with the team's mission.

**Team's Mission:** "{user_goal}"

Follow these instructions in order of priority:

1.  **Preserve Unique Roles:** Your most important rule is to preserve specialized roles. Do NOT merge personas that have clearly distinct functions, even if their domains are related (e.g., a 'On-Chain Data Analyst' and a 'Crypto Market Trend Forecaster' are distinct and should NOT be merged).

2.  **Refine and Sharpen:** For each persona, review its profile. Can its `expertise` list be made more specific and less generic? Can its `key_traits` be sharpened to give it a more unique personality? Make subtle improvements to enhance each persona.

3.  **Merge Only True Redundancies:** Only as a last resort, if two or more personas are *functionally identical* and their roles are completely overlapping (e.g., a "Hype Creator" and an "Excitement Generator"), merge them into a single, superior persona that combines their strengths.

4.  **Maintain Schema:** Your final output MUST be a valid JSON object with a single key "optimized_personas". This key must contain a list of the final persona profiles, strictly adhering to the original schema (you can omit the 'examples' field if you are only refining text).

Here is the list of persona profiles to analyze and refine:
{persona_list_json}
"""

async def run_optimizer_agent(state: PipelineState) -> PipelineState:
    """
    Executes the Optimizer agent to refine the set of generated personas,
    merging any that are redundant.
    """
    print(f"[OptimizerAgent] Optimizing {len(state.generated_personas)} generated personas...")

    if not state.generated_personas:
        print("[OptimizerAgent] No personas to optimize. Skipping.")
        state.status = 'VALIDATING'
        return state

    # --- NEW: Create lighter summaries for the prompt ---
    # We exclude 'examples' which are very long and not essential for high-level optimization.
    # This is the key change to reduce token count and time.
    persona_summaries = []
    for p in state.generated_personas:
        summary = p.model_dump(exclude={'examples'})
        persona_summaries.append(summary)
    
    persona_list_json = json.dumps(persona_summaries, indent=2)
    # --- END NEW ---

    # 1. Fill the prompt template.
    prompt = OPTIMIZER_PROMPT_TEMPLATE.format(
        user_goal=state.initial_prompt,
        persona_list_json=persona_list_json
    )

    # 2. Call the LLM service to get the optimized list.
    llm_response = await generate_json_response(
        prompt=prompt,
        openai_api_key=state.openai_api_key,
        # BUG FIX: Correct the identifier from "Validator_agent" to "optimizer_agent"
        call_identifier="optimizer_agent"
    )

    # 3. Validate the response and update the state.
    if "optimized_personas" in llm_response and isinstance(llm_response["optimized_personas"], list):
        try:
            # We need to merge the optimized data back into the original objects
            # to preserve the 'examples' that we didn't send to the LLM.
            
            # Create a map of the original personas by name
            original_personas_map = {p.persona_name: p for p in state.generated_personas}
            
            optimized_list = []
            for optimized_data in llm_response["optimized_personas"]:
                # Find the original persona to get its examples
                original_persona = original_personas_map.get(optimized_data.get("persona_name"))
                
                if original_persona:
                    # If the optimizer didn't generate new examples, use the original ones.
                    if 'examples' not in optimized_data:
                        optimized_data['examples'] = original_persona.examples
                
                # Now validate the complete object
                validated_persona = Persona(**optimized_data)
                optimized_list.append(validated_persona)

            original_count = len(state.generated_personas)
            new_count = len(optimized_list)
            
            print(f"[OptimizerAgent] Optimization complete. Original count: {original_count}, New count: {new_count}.")
            if new_count < original_count:
                print("  - Merged one or more redundant personas.")
            
            # Replace the old list with the new, optimized one.
            state.generated_personas = optimized_list
            state.status = 'VALIDATING'

        except Exception as e:
            error_message = f"OptimizerAgent failed: Pydantic validation error on the optimized list. Details: {e}"
            print(f"ERROR: {error_message}")
            print(f"LLM Response was: {llm_response}")
            state.status = 'FAILED'
            state.history.append(error_message)
    else:
        error_message = "OptimizerAgent failed: LLM output did not contain a valid 'optimized_personas' list."
        print(f"ERROR: {error_message}")
        print(f"LLM Response was: {llm_response}")
        state.status = 'FAILED'
        state.feedback_notes = error_message

    return state