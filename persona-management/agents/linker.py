# persona-management/agents/linker.py

import json
from ..schemas.pipeline_state import PipelineState
from ..schemas.persona_profile import PersonaProfile
from ..services.llm_service import generate_json_response

LINKER_PROMPT_TEMPLATE = """
You are a master AI Team Strategist. Your job is to define the collaboration "playbook" for a team of AI personas to ensure they work together effectively in a live chat.

Here is the final, validated team of AI personas:
{persona_list_json}

Based on this team, your task is to generate a set of interaction rules. These rules should define handoffs, triggers, and collaboration protocols.

Your output MUST be a JSON object with a single key "interaction_playbook". This key should contain a list of objects. Each object must have two keys:
1. "persona_name": The name of the persona the rule applies to.
2. "rules": A list of strings, where each string is a specific interaction rule for that persona.

Focus on creating triggers. For example: "If a user asks a technical question, this persona should stop and 'Handoff to Support Specialist'." or "Can post a witty comment in parallel after the 'Product Evangelist' makes an announcement."

Example Output:
{{
  "interaction_playbook": [
    {{
      "persona_name": "Product Evangelist",
      "rules": [
        "Primary responder for general questions about the product's vision and benefits.",
        "If a user asks a detailed technical question, handoff the conversation to the 'Support Specialist'.",
        "Can be followed up by the 'Hype Creator' to amplify excitement after a feature announcement."
      ]
    }},
    {{
      "persona_name": "Hype Creator",
      "rules": [
        "Should post memes or high-energy comments after the 'Product Evangelist' makes a positive announcement.",
        "Avoids answering technical questions directly."
      ]
    }}
  ]
}}
"""

async def run_linker_agent(state: PipelineState) -> PipelineState:
    """
    Executes the Linker agent to define interaction rules for the persona team.
    """
    print("[LinkerAgent] Defining interaction playbook for the persona team...")

    if not state.generated_personas:
        error_message = "LinkerAgent failed: No personas available to link."
        print(f"ERROR: {error_message}")
        state.status = 'FAILED'
        state.feedback_notes = error_message
        return state

    persona_list_dict = [p.model_dump(exclude={'interaction_rules'}) for p in state.generated_personas]
    persona_list_json = json.dumps(persona_list_dict, indent=2)

    prompt = LINKER_PROMPT_TEMPLATE.format(persona_list_json=persona_list_json)

    llm_response = await generate_json_response(prompt)

    if "interaction_playbook" in llm_response and isinstance(llm_response["interaction_playbook"], list):
        playbook = llm_response["interaction_playbook"]
        
        # Create a dictionary for easy lookup
        persona_map = {p.persona_name: p for p in state.generated_personas}
        
        for rule_set in playbook:
            persona_name = rule_set.get("persona_name")
            rules = rule_set.get("rules")
            
            if persona_name in persona_map and isinstance(rules, list):
                # Add the generated rules to the corresponding persona object
                persona_map[persona_name].interaction_rules.extend(rules)
                print(f"  - Added {len(rules)} interaction rule(s) to '{persona_name}'")
        
        # The state.generated_personas list is now updated by reference.
        state.status = 'FINAL_MODERATION' # Transition to the final safety check

    else:
        error_message = "LinkerAgent failed: LLM output did not contain a valid 'interaction_playbook'."
        print(f"ERROR: {error_message}")
        print(f"LLM Response was: {llm_response}")
        # We can consider this a non-critical failure and proceed, or fail the pipeline.
        # Let's proceed but log a warning.
        print("WARNING: Could not generate interaction rules. Personas will act independently.")
        state.status = 'FINAL_MODERATION'

    return state