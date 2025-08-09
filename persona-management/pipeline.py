# persona-management/pipeline.py

from .schemas.pipeline_state import PipelineState
from .agents import (
    planner,
    role_mapper,
    crafter,
    memory_checker,
    optimizer,
    validator,
    feedback_loop,
    linker
)

# A mapping of status to the agent function that should be run.
AGENT_MAPPING = {
    'PLANNING': planner.run_planner_agent,
    'MAPPING_ROLES': role_mapper.run_role_mapper_agent,
    'CRAFTING': crafter.run_crafter_agent,
    'CHECKING_MEMORY': memory_checker.run_memory_checker_agent,
    'OPTIMIZING': optimizer.run_optimizer_agent,
    'LINKING': linker.run_linker_agent,
    # Note: Validator and FeedbackLoop are handled specially inside the loop.
}

async def run_persona_factory_pipeline(initial_prompt: str, max_retries: int = 2) -> dict:
    """
    Orchestrates the running of the persona generation pipeline.

    This function manages the state and calls the appropriate agents in sequence,
    handling the validation and feedback loop.

    Args:
        initial_prompt: The user's high-level goal.
        max_retries: The maximum number of times to retry if validation fails.

    Returns:
        A dictionary containing the final list of generated personas on success,
        or an error message on failure.
    """
    state = PipelineState(initial_prompt=initial_prompt, status='PLANNING')
    retry_count = 0

    print("--- Starting Persona Factory Pipeline ---")

    while state.status not in ['SUCCESS', 'FAILED']:
        current_status = state.status
        print(f"\n[Pipeline] Current State: {current_status}")

        if current_status in AGENT_MAPPING:
            agent_function = AGENT_MAPPING[current_status]
            state = await agent_function(state)

        elif current_status == 'VALIDATING':
            # The validator agent is special as it controls the loop.
            is_valid, errors = await validator.run_validator_agent(state)
            if is_valid:
                # If valid, we proceed to the Linker.
                state.status = 'LINKING'
            else:
                # If invalid, check if we can retry.
                if retry_count < max_retries:
                    retry_count += 1
                    print(f"[Pipeline] Validation failed. Initiating retry #{retry_count}...")
                    state.validation_errors = errors
                    state = await feedback_loop.run_feedback_loop_agent(state) # This will change status to 'REFINING'
                else:
                    print(f"[Pipeline] Validation failed after {max_retries} retries. Aborting.")
                    state.status = 'FAILED'
                    state.feedback_notes = f"Validation failed and max retries were reached. Last errors: {errors}"
        
        elif current_status == 'REFINING':
            # After feedback is generated, we loop back to the Role Mapper.
            print(f"[Pipeline] Refining roles based on feedback: {state.feedback_notes}")
            state.status = 'MAPPING_ROLES'
        
        elif current_status == 'FINAL_MODERATION':
            # For now, we'll consider this the final success state.
            # A real moderation agent could be added here.
            print("[Pipeline] Final moderation check passed (skipped).")
            state.status = 'SUCCESS'

        else:
            # This is a catch-all for unknown states.
            print(f"ERROR: [Pipeline] Unknown pipeline state: {current_status}")
            state.status = 'FAILED'
            state.feedback_notes = f"Pipeline entered an unknown state: {current_status}"

    print("\n--- Persona Factory Pipeline Finished ---")
    
    if state.status == 'SUCCESS':
        print("Pipeline completed successfully.")
        # Convert Pydantic models to a list of dicts for clean JSON output
        final_personas = [p.model_dump() for p in state.generated_personas]
        return {"status": "success", "personas": final_personas}
    else:
        print(f"Pipeline failed. Reason: {state.feedback_notes}")
        return {"status": "failed", "reason": state.feedback_notes}