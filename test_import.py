#!/usr/bin/env python3
"""
Test script to verify the persona-management import works correctly.
"""

import sys
import os
import importlib.util

# Add the project root to Python path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    # Test the new import method
    persona_management_dir = os.path.join(project_root, 'persona-management')
    print(f"Looking for persona-management at: {persona_management_dir}")
    print(f"Directory exists: {os.path.exists(persona_management_dir)}")
    
    if os.path.exists(persona_management_dir):
        sys.path.insert(0, persona_management_dir)
        from pipeline import run_persona_factory_pipeline
        
        print("✅ Successfully imported run_persona_factory_pipeline!")
        print(f"Function: {run_persona_factory_pipeline}")
    else:
        print("❌ persona-management directory not found!")
        
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()