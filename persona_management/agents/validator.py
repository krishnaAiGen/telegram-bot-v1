# persona-management/agents/validator.py

import json
from typing import Tuple, List
from ..schemas.pipeline_state import PipelineState
from ..services.llm_service import generate_json_response

VALIDATOR_PROMPT_TEMPLATE = """
You are a meticulous AI System Validator. Your job is to ensure that a team of AI personas is complete and capable of executing a given list of tasks.

Here is the original list of required tasks:
{task_list}

Here is the final, optimized team of AI personas:
{persona_list_json}

Carefully review both lists. Your task is to determine if the persona team can successfully handle ALL of the required tasks.

Your output must be a JSON object with two keys:
1.  "is_valid": A boolean value (`true` if all tasks are covered, `false` otherwise).
2.  "errors": A list of strings. If "is_valid" is `false`, this list should contain a description of what is missing or wrong. If "is_valid" is `true`, this should be an empty list.

Example 1 (Success):
Tasks: ["Create hype", "Answer questions"]
Personas: ["Hype Creator", "Support Specialist"]
Your Output:
{{
  "is_valid": true,
  "errors": []
}}

Example 2 (Failure):
Tasks: ["Create hype", "Answer questions", "Moderate chat"]
Personas: ["Hype Creator", "Support Specialist"]
Your Output:
{{
  "is_valid": false,
  "errors": ["The persona team is missing a role for 'Moderate chat'. There is no Community Moderator."]
}}
"""

async def run_validator_agent(state: PipelineState) -> Tuple[bool, List[str]]:
    """
    Executes the Validator agent to check if the persona team covers all tasks.

    Args:
        state: The current pipeline state, containing planned_tasks and generated_personas.

    Returns:
        A tuple containing a boolean (is_valid) and a list of error strings.
    """
    print("[ValidatorAgent] Validating final persona team against original tasks...")

    if not state.planned_tasks or not state.generated_personas:
        error_message = "ValidatorAgent cannot run: Missing tasks or personas in the state."
        print(f"ERROR: {error_message}")
        return False, [error_message]

    # Format inputs for the prompt
    formatted_task_list = "\n".join(f"- \"{task}\"" for task in state.planned_tasks)
    persona_list_dict = [p.model_dump() for p in state.generated_personas]
    persona_list_json = json.dumps(persona_list_dict, indent=2)

    prompt = VALIDATOR_PROMPT_TEMPLATE.format(
        task_list=formatted_task_list,
        persona_list_json=persona_list_json
    )
    
    llm_response = await generate_json_response(prompt)

    is_valid = llm_response.get("is_valid", False)
    errors = llm_response.get("errors", ["LLM response was malformed."])

    if is_valid:
        print("[ValidatorAgent] Validation PASSED. The persona team covers all required tasks.")
    else:
        print(f"[ValidatorAgent] Validation FAILED. Reason(s): {errors}")
        
    return is_valid, errors