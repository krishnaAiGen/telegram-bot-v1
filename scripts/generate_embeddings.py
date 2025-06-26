# scripts/generate_embeddings.py
import asyncio
import json
import os
import sys

# Add the project root to the Python path to allow imports from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core_logic.llm_personas import PersonaManager
from src.services.openai_chat import get_embedding

async def main():
    """Generates embeddings for all personas and saves them to a file."""
    print("Initializing PersonaManager to load characters...")
    persona_manager = PersonaManager()
    all_personas = persona_manager.all_personas
    
    persona_embeddings = {}
    
    print(f"Found {len(all_personas)} personas. Generating embeddings...")
    
    for persona in all_personas:
        # Create a descriptive text for each persona
        description = (
            f"Role: {persona.get('role', '')}. "
            f"Expertise: {', '.join(persona.get('expertise', []))}. "
            f"Traits: {', '.join(persona.get('key_traits', []))}. "
            f"Voice: {persona.get('signature_voice', {}).get('tone', '')}."
        )
        
        print(f"  - Generating embedding for '{persona['persona_name']}'...")
        embedding = await get_embedding(description)
        
        if embedding:
            persona_embeddings[persona['persona_name']] = embedding
            print(f"    ... success.")
        else:
            print(f"    ... FAILED.")

    # Save the embeddings to a file
    output_path = os.path.join('data', 'persona_embeddings.json')
    os.makedirs('data', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(persona_embeddings, f, indent=2)
        
    print(f"\nSuccessfully generated and saved {len(persona_embeddings)} embeddings to '{output_path}'.")

if __name__ == "__main__":
    # This requires an OpenAI key in the .env file
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("CRITICAL: OPENAI_API_KEY not found in .env file. Cannot generate embeddings.")
    else:
        asyncio.run(main())