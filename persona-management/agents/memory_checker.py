# persona-management/agents/memory_checker.py

from ..schemas.pipeline_state import PipelineState
from ..services.llm_service import generate_text_response
import json

MEMORY_CHECKER_PROMPT_TEMPLATE = """
You are an AI System Analyst. Your task is to review a set of newly generated AI persona profiles and check for semantic redundancy. Do not merge or change them; simply identify if any two or more personas are functionally too similar.

Here is the set of persona profiles:
{persona_list_json}

Analyze their roles, expertise, and tones. Answer with a simple "YES" if you find significant functional overlap between any of the personas, or "NO" if they are all sufficiently distinct. Provide a brief one-sentence justification for your answer.

Example 1:
- Persona A: "Hype Creator" - Creates viral content.
- Persona B: "Marketing Guru" - Generates buzz.
Your Answer: YES - Both personas are focused on generating hype and buzz, their functions are nearly identical.

Example 2:
- Persona A: "Hype Creator" - Creates viral content.
- Persona B: "Support Specialist" - Answers technical questions.
Your Answer: NO - These personas have distinct and complementary roles.
"""

async def run_memory_checker_agent(state: PipelineState) -> PipelineState:
    """
    Executes the Memory Checker agent to check for redundancy in the generated personas.
    For now, this is a simple check within the generated set.
    """
    print(f"[MemoryCheckerAgent] Checking {len(state.generated_personas)} personas for redundancy...")

    if len(state.generated_personas) < 2:
        print("[MemoryCheckerAgent] Fewer than 2 personas, no need to check for redundancy.")
        state.status = 'OPTIMIZING' # Skip to the next step
        return state

    # Convert the list of Pydantic models to a list of dictionaries for JSON serialization
    persona_list_dict = [p.model_dump() for p in state.generated_personas]
    
    # Prettify the JSON for better readability in the prompt
    persona_list_json = json.dumps(persona_list_dict, indent=2)

    prompt = MEMORY_CHECKER_PROMPT_TEMPLATE.format(persona_list_json=persona_list_json)

    # We use a simple text response here, not JSON
    llm_response = await generate_text_response(prompt)

    print(f"[MemoryCheckerAgent] LLM Analysis: {llm_response}")

    # This is a simple implementation. A more advanced version might parse the response
    # and flag specific personas for the Optimizer agent. For now, we'll just log the result.
    if "YES" in llm_response.upper():
        print("[MemoryCheckerAgent] Potential redundancy detected. The Optimizer agent will handle this.")
    else:
        print("[MemoryCheckerAgent] Personas appear to be distinct.")

    # In either case, we transition to the Optimizer to perform the actual work.
    state.status = 'OPTIMIZING'
    
    return state