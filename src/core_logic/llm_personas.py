import random

class PersonaManager:
    """
    Manages a specific user's set of persona definitions, provided
    at initialization.
    """
    def __init__(self, personas: list):
        """
        Initializes the PersonaManager with a list of persona dictionaries.

        Args:
            personas: A list of persona dictionaries (e.g., from a user's liveTeam).
        """
        if not personas:
            # It's possible for a user to have no personas, but we should log this.
            print("WARNING: PersonaManager initialized with an empty list of personas.")
            self.all_personas = []
        else:
            # The liveTeam from Firestore is already a flat list of personas.
            self.all_personas = personas
        
        print(f"[PERSONA_MANAGER] Initialized with {len(self.all_personas)} personas.")

    def get_persona_by_name(self, name: str) -> dict | None:
        """Finds a persona by its name in the current user's list."""
        return next((p for p in self.all_personas if p.get('persona_name') == name), None)

    def get_random_persona(self) -> dict | None:
        """Selects a random persona from the current user's list."""
        return random.choice(self.all_personas) if self.all_personas else None