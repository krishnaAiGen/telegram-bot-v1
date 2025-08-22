#!/usr/bin/env python3
"""
Simple script to run the Persona Management Dashboard backend server.
"""

import uvicorn
import sys
import os

# Add the project root to Python path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if __name__ == "__main__":
    print("🚀 Starting Persona Management Dashboard...")
    print("📊 Dashboard will be available at: http://localhost:8000")
    print("🌐 Frontend will be served at: http://localhost:8000/dashboard")
    print("📋 API docs available at: http://localhost:8000/docs")
    print("\n💡 Use Ctrl+C to stop the server")
    print("-" * 50)
    
    try:
        uvicorn.run(
            "dashboard.backend.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,  # Auto-reload on code changes
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Dashboard server stopped.")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)