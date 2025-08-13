# persona-management/schemas/persona_profile.py

from pydantic import BaseModel, Field
from typing import List, Dict, Any

class SignatureVoice(BaseModel):
    tone: str
    style: str
    language_habits: List[str] = Field(default_factory=list)

class KnowledgeBoundaries(BaseModel):
    will_defer_on: List[str] = Field(default_factory=list)
    refusal_message: str

class ExampleInteraction(BaseModel):
    user: str
    assistant: str

class Persona(BaseModel):
    """
    Defines a single, specific persona profile. This is the inner object.
    """
    persona_name: str
    tagline: str
    role: str
    expertise: List[str]
    signature_voice: SignatureVoice
    allow_emojis: bool
    key_traits: List[str]
    knowledge_boundaries: KnowledgeBoundaries
    examples: List[ExampleInteraction]
    # interaction_rules here at the individual persona level
    interaction_rules: List[str] = Field(default_factory=list, description="Rules for how this persona interacts with others.")

class Character(BaseModel):
    """
    Defines a 'Character' which is a container for multiple personas.
    This character is often tied to a specific bot user account.
    """
    character_name: str
    # configurable telegram_user
    telegram_user: str 
    personas: List[Persona]