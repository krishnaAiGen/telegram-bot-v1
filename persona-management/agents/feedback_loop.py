# persona-management/agents/feedback_loop.py

from ..schemas.pipeline_state import PipelineState
from ..services.llm_service import generate_text_response

FEEDBACK_PROMPT_TEMPLATE = """
You are a System Refinement expert in a multi-agent AI system. The system just failed a validation check while trying to generate a team of AI personas.

The original goal was: "{user_goal}"

The team of personas generated was:
{persona_list_json}

The validation failed with the following errors:
{error_list}

Your single task is to generate a concise, one-sentence refinement instruction for the Role Mapper agent to use on its next attempt. This instruction should guide it to fix the specific errors found.

Example:
Errors: ["The team is missing a role for 'Moderate chat'."]
Your Output:
Refine the persona roles by adding a 'Community Moderator' responsible for handling feedback and maintaining a positive chat environment.
"""

async def run_feedback_loop_agent(state: PipelineState) -> PipelineState:
    """
    If validation fails, this agent generates feedback notes to guide a retry.
    """
    print("[FeedbackLoopAgent] Generating refinement instructions for a retry...")

    if not state.validation_errors:
        # This should not happen if the pipeline logic is correct, but it's a safe check.
        state.status = 'FAILED'
        state.feedback_notes = "FeedbackLoopAgent called without validation errors."
        return state

    # Format inputs for the prompt
    import json
    persona_list_dict = [p.model_dump() for p in state.generated_personas]
    persona_list_json = json.dumps(persona_list_dict, indent=2)
    error_list_str = "\n".join(f"- {error}" for error in state.validation_errors)

    prompt = FEEDBACK_PROMPT_TEMPLATE.format(
        user_goal=state.initial_prompt,
        persona_list_json=persona_list_json,
        error_list=error_list_str
    )

    # We just need a simple text response here
    refinement_instruction = await generate_text_response(prompt)
    
    print(f"[FeedbackLoopAgent] Generated instruction: {refinement_instruction}")

    # Update the state for the retry
    state.feedback_notes = refinement_instruction
    state.status = 'REFINING' # This status tells the pipeline to re-run the Role Mapper

    return state