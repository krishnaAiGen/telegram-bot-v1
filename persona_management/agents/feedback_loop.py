# persona-management/agents/feedback_loop.py

from ..schemas.pipeline_state import PipelineState
from ..services.llm_service import generate_text_response

FEEDBACK_PROMPT_TEMPLATE = """
You are a System Refinement expert in a multi-agent AI system. The system failed a validation check while generating AI personas. Your task is to provide a structured, machine-readable instruction to fix the error.

**Original Goal:** "{user_goal}"

**Generated Personas:**
{persona_list_json}

**Validation Errors:**
{error_list}

Based on the errors, generate a JSON object with two keys: "action" and "details".
- The "action" can be one of: "ADD_ROLE", "MODIFY_ROLE", or "CLARIFY_AMBIGUITY".
- The "details" should contain the information needed to perform the action.

Your response MUST be ONLY the valid JSON object.

Example 1:
Errors: ["The team is missing a role for 'Moderate chat'."]
Your Output:
{{
  "action": "ADD_ROLE",
  "details": {{
    "role": "Community Moderator",
    "description": "Responsible for handling user feedback, maintaining a positive environment, and enforcing community rules."
  }}
}}

Example 2:
Errors: ["The 'Support Specialist' persona does not have expertise related to pricing."]
Your Output:
{{
  "action": "MODIFY_ROLE",
  "details": {{
    "role_to_modify": "Support Specialist",
    "reason_for_change": "The current persona lacks the necessary expertise to answer questions about pricing, which was a required task. Its expertise list should be updated.",
    "suggested_additions": ["Provide clear information on product pricing and subscription tiers."]
  }}
}}
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
    refinement_instruction = await generate_json_response(
    prompt=prompt,
    openai_api_key=state.openai_api_key,
    call_identifier="Feedback_agent"
)
    
    print(f"[FeedbackLoopAgent] Generated instruction: {refinement_instruction}")

    # Update the state for the retry
    state.feedback_notes = refinement_instruction
    state.status = 'REFINING' # This status tells the pipeline to re-run the Role Mapper

    return state