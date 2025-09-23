# persona-management/agents/formatter.py

from ..schemas.pipeline_state import PipelineState
from ..schemas.persona_profile import Character, Persona
from typing import List

def run_formatter_agent(state: PipelineState) -> List[Character]:
    """
    This agent is not AI-driven. It's a simple utility that formats the final
    list of personas into the required nested character structure.

    For now, it will group all generated personas under a single "Generated Character".
    """
    print("[FormatterAgent] Formatting final output into character structure...")

    if not state.generated_personas:
        print("[FormatterAgent] No personas to format.")
        return []

    # For this version, we will assign all generated personas to a single character
    # with a default name and user account. This can be made more configurable later.
    generated_character = Character(
        character_name="Generated Character",
        telegram_user="default_sender_account",
        personas=state.generated_personas
    )
    
    final_character_list = [generated_character]
    
    print(f"[FormatterAgent] Successfully formatted {len(state.generated_personas)} personas into {len(final_character_list)} character(s).")
    
    return final_character_list