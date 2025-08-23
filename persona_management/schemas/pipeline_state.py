# persona-management/schemas/pipeline_state.py

from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any
from .persona_profile import Persona

class PersonaBlueprint(BaseModel):
    """A high-level plan for a persona before it's fully crafted."""
    role: str
    description: str

class PipelineState(BaseModel):
    """
    Holds the state of the persona generation process as it moves through the pipeline.
    This object is passed from one agent to the next.
    """
    initial_prompt: str
    status: Literal[
        'PLANNING', 'MAPPING_ROLES', 'CRAFTING', 'CHECKING_MEMORY', 
        'OPTIMIZING', 'VALIDATING', 'REFINING', 'LINKING', 
        'FINAL_MODERATION', 'SUCCESS', 'FAILED'
    ] = 'PLANNING'
    
    # Data fields that get populated by agents
    planned_tasks: List[str] = Field(default_factory=list)
    persona_blueprints: List[PersonaBlueprint] = Field(default_factory=list)
    generated_personas: List[Persona] = Field(default_factory=list)
    
    # For feedback and control flow
    feedback_notes: str | None = None
    validation_errors: List[str] = Field(default_factory=list)