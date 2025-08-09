# persona-management/agents/optimizer.py

import json
from ..schemas.pipeline_state import PipelineState
from ..schemas.persona_profile import PersonaProfile
from ..services.llm_service import generate_json_response

OPTIMIZER_PROMPT_TEMPLATE = """
You are a master AI System Optimizer. Your task is to analyze a list of AI persona profiles and refine it for maximum efficiency and clarity.

Your instructions are:
1.  **Merge Redundant Personas:** If two or more personas have very similar roles, expertise, or tones (e.g., a "Hype Creator" and an "Excitement Generator"), merge them into a single, well-defined persona. The new persona should combine the strengths of the originals. Give it a clear, encompassing name.
2.  **Preserve Distinct Roles:** Do NOT merge personas that have clearly distinct functions (e.g., a "Support Specialist" and a "Community Moderator").
3.  **Ensure Completeness:** Make sure the final set of personas still covers all the necessary functions implied by their roles.
4.  **Maintain Schema:** Your final output MUST be a valid JSON object with a single key "optimized_personas". This key should contain a list of the final, optimized persona profiles, strictly adhering to the original JSON schema for each persona.

Here is the list of persona profiles to optimize:
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

    # Convert the list of Pydantic models to a list of dictionaries for the prompt
    persona_list_dict = [p.model_dump() for p in state.generated_personas]
    persona_list_json = json.dumps(persona_list_dict, indent=2)

    # 1. Fill the prompt template.
    prompt = OPTIMIZER_PROMPT_TEMPLATE.format(persona_list_json=persona_list_json)

    # 2. Call the LLM service to get the optimized list.
    llm_response = await generate_json_response(prompt)

    # 3. Validate the response and update the state.
    if "optimized_personas" in llm_response and isinstance(llm_response["optimized_personas"], list):
        try:
            # Validate the new, optimized list against our strict PersonaProfile schema
            optimized_list = [PersonaProfile(**p) for p in llm_response["optimized_personas"]]
            
            original_count = len(state.generated_personas)
            new_count = len(optimized_list)
            
            print(f"[OptimizerAgent] Optimization complete. Original count: {original_count}, New count: {new_count}.")
            if new_count < original_count:
                print("  - Merged one or more redundant personas.")
            
            # Replace the old list with the new, optimized one.
            state.generated_personas = optimized_list
            state.status = 'VALIDATING' # Transition to the next state

        except Exception as e:
            error_message = f"OptimizerAgent failed: Pydantic validation error on the optimized list. Details: {e}"
            print(f"ERROR: {error_message}")
            print(f"LLM Response was: {llm_response}")
            state.status = 'FAILED'
            state.feedback_notes = error_message
    else:
        error_message = "OptimizerAgent failed: LLM output did not contain a valid 'optimized_personas' list."
        print(f"ERROR: {error_message}")
        print(f"LLM Response was: {llm_response}")
        state.status = 'FAILED'
        state.feedback_notes = error_message

    return state