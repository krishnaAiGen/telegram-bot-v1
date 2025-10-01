# persona-management/agents/planner.py

from ..schemas.pipeline_state import PipelineState
from ..services.llm_service import generate_json_response

# This is the "meta-prompt" for the Planner agent.
PLANNER_PROMPT_TEMPLATE = """
You are a master Task Planner for an advanced AI persona bot system. Your job is to decompose a user's high-level goal into a clear, logical list of actionable sub-tasks that a team of AI personas will need to execute.

The user's goal is:
"{user_goal}"

Based on this goal, identify the core functions the bot will need to perform. Consider aspects like content creation, community interaction, information delivery, and maintaining a specific atmosphere.

Please provide your output as a JSON object with a single key "tasks", which is a list of strings. Each string should be a distinct sub-task.

Example:
User Goal: "I want a bot to promote my new sneaker drop on Telegram."
Your Output:
{{
  "tasks": [
    "Generate hype and excitement for the upcoming sneaker drop.",
    "Announce key dates, times, and links for the drop.",
    "Answer frequently asked questions about the sneakers (e.g., price, materials, availability).",
    "Create and share viral, meme-style content related to sneaker culture.",
    "Engage with user comments and build a sense of community.",
    "Moderate the chat to handle feedback and maintain a positive environment."
  ]
}}
"""

async def run_planner_agent(state: PipelineState) -> PipelineState:
    """
    Executes the Planner agent to decompose the user's goal into sub-tasks.

    Args:
        state: The current state of the persona generation pipeline.

    Returns:
        The updated pipeline state with the `planned_tasks` field populated.
    """
    print("[PlannerAgent] Decomposing user goal into sub-tasks...")

    # 1. Fill the prompt template with the user's goal from the state object.
    prompt = PLANNER_PROMPT_TEMPLATE.format(user_goal=state.initial_prompt)

    # 2. Call our centralized LLM service, now passing the user-specific API key.
    llm_response = await generate_json_response(
        prompt=prompt,
        openai_api_key=state.openai_api_key,
        call_identifier="planner_agent"  # NEW: Add this line
    )

    # 3. Validate the response and update the state.
    if llm_response and "tasks" in llm_response and isinstance(llm_response["tasks"], list):
        tasks = llm_response["tasks"]
        validated_tasks = [str(task) for task in tasks if str(task).strip()]
        
        state.planned_tasks = validated_tasks
        state.status = 'MAPPING_ROLES' # Transition to the next state
        
        print(f"[PlannerAgent] Successfully planned {len(validated_tasks)} tasks.")
        for i, task in enumerate(validated_tasks, 1):
            print(f"  - Task {i}: {task}")
            
    else:
        # If the LLM response is not in the expected format, mark the pipeline as failed.
        error_message = "PlannerAgent failed: LLM output did not contain a valid 'tasks' list."
        print(f"ERROR: {error_message}")
        state.status = 'FAILED'
        state.history.append(error_message)

    return state