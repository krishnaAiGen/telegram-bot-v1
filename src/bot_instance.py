# src/bot_instance.py

from dataclasses import dataclass, field
from typing import List, Dict, Any

# We will need to refactor these later, but for now, we import them
# to see how they will connect to the instance.
from src.core_logic.llm_personas import PersonaManager
from src.services.state_manager import StateManager

@dataclass
class BotInstance:
    """
    A self-contained container for all data, configuration, and state
    related to a single tenant's running bot instance.
    """
    user_id: str
    user_config: Dict[str, Any]
    
    # These fields will be populated from the user_config dictionary upon initialization
    live_team: List[Dict[str, Any]] = field(init=False)
    credentials: Dict[str, Any] = field(init=False)
    behavior_settings: Dict[str, Any] = field(init=False)
    
    # User-specific service managers
    persona_manager: PersonaManager = field(init=False)
    state_manager: StateManager = field(init=False)
    
    # Placeholder for the actual, live platform clients (e.g., Telethon client)
    platform_clients: Dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self):
        """
        This special dataclass method runs after the object is created.
        It's the perfect place to unpack the user_config and initialize
        our user-specific components.
        """
        print(f"--- Initializing BotInstance for user: {self.user_id} ---")

        # 1. Unpack the main configuration dictionary
        self.live_team = self.user_config.get("liveTeam", [])
        self.credentials = self.user_config.get("connections", {})
        self.behavior_settings = self.user_config.get("botConfig", {}) # e.g., for response rates

        # 2. Initialize user-specific, stateful services
        #    NOTE: This will require refactoring StateManager and PersonaManager later
        #    to accept this new kind of initialization.
        
        # This will fail until PersonaManager is refactored, but it shows the intent
        try:
            self.persona_manager = PersonaManager(personas=self.live_team)
            print(f"  -> PersonaManager initialized with {len(self.live_team)} personas.")
        except Exception as e:
            print(f"  -> WARNING: Could not initialize PersonaManager. Needs refactoring. Error: {e}")
            self.persona_manager = None

        # This will fail until StateManager is refactored, but it shows the intent
        try:
            # We assume a primary connectionId might be passed in behavior_settings
            # This logic will become more robust later.
            primary_connection = self.behavior_settings.get("primary_connection_id", "default")
            self.state_manager = StateManager(user_id=self.user_id, connection_id=primary_connection)
            print(f"  -> StateManager initialized for connection: {primary_connection}")
        except Exception as e:
            print(f"  -> WARNING: Could not initialize StateManager. Needs refactoring. Error: {e}")
            self.state_manager = None
            
        print(f"--- BotInstance for {self.user_id} is ready. ---")