# src/bot_instance.py
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any

from src.core_logic.llm_personas import PersonaManager
from src.services.state_manager import StateManager
from src.services.openai_chat import get_embedding

@dataclass
class BotInstance:
    user_id: str
    user_config: Dict[str, Any]
    
    live_team: List[Dict[str, Any]] = field(init=False)
    credentials: Dict[str, Any] = field(init=False)
    behavior_settings: Dict[str, Any] = field(init=False)
    persona_manager: PersonaManager = field(init=False)
    state_manager: StateManager = field(init=False)
    persona_embeddings: Dict[str, List[float]] = field(init=False, default_factory=dict)
    persona_names: List[str] = field(init=False, default_factory=list)

    def __post_init__(self):
        persona_config = self.user_config.get("personaConfig", {})
        self.live_team = persona_config.get("liveTeam", [])
        self.credentials = self.user_config.get("connections", {})
        self.behavior_settings = persona_config
        self.persona_manager = PersonaManager(personas=self.live_team)

    async def _initialize_embeddings(self):
        print(f"  -> Initializing embeddings for user {self.user_id}...")
        openai_api_key = self.credentials.get("openai", {}).get("api_key")

        if not openai_api_key or not self.persona_manager.all_personas:
            print(f"  -> WARNING: Skipping embedding generation. Key found: {bool(openai_api_key)}, Personas: {bool(self.persona_manager.all_personas)}")
            return

        tasks = [get_embedding(f"Role: {p.get('role', '')}", api_key=openai_api_key) for p in self.persona_manager.all_personas]
        embeddings_results = await asyncio.gather(*tasks)
        
        for i, p in enumerate(self.persona_manager.all_personas):
            if embeddings_results[i]:
                persona_name = p.get('persona_name')
                if persona_name:
                    self.persona_embeddings[persona_name] = embeddings_results[i]
                    self.persona_names.append(persona_name)
        
        print(f"  -> Successfully cached {len(self.persona_embeddings)} embeddings for user {self.user_id}.")

    async def initialize(self, db):
        primary_connection_id = self.behavior_settings.get("primary_connection_id", "default_connection")
        self.state_manager = StateManager(db=db, user_id=self.user_id, connection_id=primary_connection_id)
        await self._initialize_embeddings()
        print(f"--- BotInstance for {self.user_id} is fully initialized and ready. ---")