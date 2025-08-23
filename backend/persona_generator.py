# backend/persona_generator.py

# Import the necessary agents, schemas, and pipeline state from your original module
from persona_management.pipeline import PipelineState
from persona_management.agents import planner, role_mapper, crafter, memory_checker, optimizer, validator, feedback_loop, linker
from persona_management.pipeline import AGENT_MAPPING

async def generate_personas_from_goal(initial_prompt: str, max_retries: int = 2) -> list | None:
    """
    A refactored, callable version of your persona factory pipeline.
    It takes a user's goal and returns a list of persona dictionaries.
    """
    print("--- Starting Persona Factory Pipeline ---")
    state = PipelineState(initial_prompt=initial_prompt, status='PLANNING')
    retry_count = 0

    # This is the main processing loop from your pipeline.py
    while state.status not in ['SUCCESS', 'FAILED']:
        current_status = state.status
        print(f"[Pipeline] Current State: {current_status}")

        if current_status == 'VALIDATING':
            is_valid, errors = await validator.run_validator_agent(state)
            if is_valid:
                state.status = 'LINKING'
            else:
                state.validation_errors = errors
                if retry_count < max_retries:
                    state = await feedback_loop.run_feedback_loop_agent(state)
                    retry_count += 1
                else:
                    state.status = 'FAILED'
        elif current_status == 'REFINING':
            state.status = 'MAPPING_ROLES'
        elif current_status in AGENT_MAPPING:
            agent_function = AGENT_MAPPING[current_status]
            state = await agent_function(state)
        elif current_status == 'FINAL_MODERATION':
            state.status = 'SUCCESS'
        else:
            state.status = 'FAILED'
            state.error_message = f"Unknown pipeline status: {current_status}"

    print("--- Persona Factory Pipeline Finished ---")

    if state.status == 'SUCCESS':
        # Extract the pure data; Pydantic's .model_dump() converts objects to dicts
        final_personas = [p.model_dump() for p in state.generated_personas]
        return final_personas
    else:
        print(f"Pipeline failed with error: {state.error_message}")
        return None # Return None on failure