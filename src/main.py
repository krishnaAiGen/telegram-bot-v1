# src/main.py

import asyncio
import os
import sys
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.orchestrator import run_orchestrator, shutdown_event
from src.config.settings import load_server_config

async def main():
    try:
        server_config = load_server_config()
        await run_orchestrator(server_config)
    except (ValueError, FileNotFoundError) as e:
        print(f"CRITICAL CONFIGURATION ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[MAIN] Shutdown requested by user.")
        shutdown_event.set()