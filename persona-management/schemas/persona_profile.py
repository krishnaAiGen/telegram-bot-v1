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

class PersonaProfile(BaseModel):
    """
    Defines the complete, detailed structure for a single AI persona.
    This schema matches the format used in characters.json.
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