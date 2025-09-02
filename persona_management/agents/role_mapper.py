# persona-management/agents/role_mapper.py

from typing import List, Dict, Any
from ..schemas.pipeline_state import PipelineState, PersonaBlueprint
from ..services.llm_service import generate_json_response

ROLE_MAPPER_PROMPT_TEMPLATE = """
You are a master AI Architect designing a team of specialized AI personas. Your job is to analyze a list of tasks and define the essential roles required to execute them.

Here is the list of tasks for the bot team:
{task_list}

Based on these tasks, define a set of unique and non-overlapping persona roles. For each role, provide a "role" title and a concise "description" of its primary function. Group related tasks under a single, well-defined role. Avoid creating too many roles; aim for a small, efficient team.

Provide your output as a JSON object with a single key "persona_blueprints", which is a list of objects. Each object must have a "role" and a "description" key.

Example:
Task List:
- "Generate hype for a sneaker drop."
- "Answer FAQs about price and availability."
- "Create viral, meme-style content."

Your Output:
{{
  "persona_blueprints": [
    {{
      "role": "Hype Creator",
      "description": "Generates excitement and viral content, including memes, to build buzz around the product."
    }},
    {{
      "role": "Support Specialist",
      "description": "Answers specific, factual user questions about the product, such as price, features, and availability."
    }}
  ]
}}
"""

async def run_role_mapper_agent(state: PipelineState) -> PipelineState:
    """
    Executes the Role Mapper agent to define persona roles based on planned tasks.

    Args:
        state: The current state of the pipeline, which must include `planned_tasks`.

    Returns:
        The updated pipeline state with `persona_blueprints` populated.
    """
    print("[RoleMapperAgent] Mapping tasks to persona roles...")

    if not state.planned_tasks:
        error_message = "RoleMapperAgent failed: No tasks were provided from the PlannerAgent."
        print(f"ERROR: {error_message}")
        state.status = 'FAILED'
        state.feedback_notes = error_message
        return state

    # Format the list of tasks for clean insertion into the prompt.
    formatted_task_list = "\n".join(f"- \"{task}\"" for task in state.planned_tasks)
    
    # 1. Fill the prompt template with the task list.
    prompt = ROLE_MAPPER_PROMPT_TEMPLATE.format(task_list=formatted_task_list)

    # 2. Call the LLM service.
    llm_response = await generate_json_response(prompt)

    # 3. Validate the response and update the state.
    if "persona_blueprints" in llm_response and isinstance(llm_response["persona_blueprints"], list):
        try:
            # Use Pydantic to parse and validate each blueprint object.
            # This is much safer than just trusting the structure.
            blueprints = [PersonaBlueprint(**bp) for bp in llm_response["persona_blueprints"]]
            
            state.persona_blueprints = blueprints
            state.status = 'CRAFTING' # Transition to the next state

            print(f"[RoleMapperAgent] Successfully defined {len(blueprints)} persona roles.")
            for bp in blueprints:
                print(f"  - Role: {bp.role} -> {bp.description}")

        except Exception as e:
            # This catches errors if the LLM output has the right key but wrong internal structure.
            error_message = f"RoleMapperAgent failed: Pydantic validation error. Details: {e}"
            print(f"ERROR: {error_message}")
            state.status = 'FAILED'
            state.feedback_notes = error_message
    else:
        error_message = "RoleMapperAgent failed: LLM output did not contain a valid 'persona_blueprints' list."
        print(f"ERROR: {error_message}")
        print(f"LLM Response was: {llm_response}")
        state.status = 'FAILED'
        state.feedback_notes = error_message

    return state