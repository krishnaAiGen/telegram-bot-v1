import random
from config.settings import CHARACTERS_DATA

class PersonaManager:
    """Manages persona definitions from characters.json."""
    def __init__(self):
        self.utility_prompts = CHARACTERS_DATA.get("utility_personas", {})
        self.all_personas = []
        for character in CHARACTERS_DATA.get("characters", []):
            for persona in character.get("personas", []):
                persona_copy = persona.copy()
                persona_copy['character_name'] = character.get('character_name')
                persona_copy['telegram_user'] = character.get('telegram_user')
                self.all_personas.append(persona_copy)
        
        if not self.all_personas:
            raise ValueError("No personas found in characters.json.")
        print(f"Initialized PersonaManager with {len(self.all_personas)} main personas.")

    def get_persona_by_name(self, name: str) -> dict | None:
        return next((p for p in self.all_personas if p['persona_name'] == name), None)

    def get_random_persona(self) -> dict | None:
        return random.choice(self.all_personas) if self.all_personas else None