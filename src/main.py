# src/main.py
import asyncio
import os
import sys

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config.settings import load_server_config
from src.orchestrator import run_orchestrator, shutdown_event

async def main():
    """Main entry point for the live bot engine service."""
    try:
        server_config = load_server_config()
        # The main async function we call is run_orchestrator
        await run_orchestrator(server_config)
    except ValueError as e:
        print(f"CRITICAL CONFIGURATION ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during startup: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[MAIN] Shutdown requested by user.")
        # When Ctrl+C is pressed, we set the async event to trigger a graceful shutdown
        shutdown_event.set()