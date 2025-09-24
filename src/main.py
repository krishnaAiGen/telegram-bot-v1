# File: src/main.py

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# Ensure platform-specific event loop policies are set if necessary
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Ensure the project root is in the Python path for correct imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import our new logging configuration setup function
from src.config.logging_config import setup_logging

# Import the core orchestrator components
from src.orchestrator import run_orchestrator, shutdown_event
from src.config.settings import load_server_config

async def main():
    """
    The main entry point for the bot orchestrator application.
    """
    # --- THIS IS THE KEY ADDITION ---
    # Configure the logging system for the entire application as the very first step.
    setup_logging()
    # --------------------------------

    # Get a logger instance specific to this main file
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Application starting up...")
        server_config = load_server_config()
        await run_orchestrator(server_config)
    except (ValueError, FileNotFoundError) as e:
        # Use logger.critical for errors that prevent the app from starting
        logger.critical(f"CRITICAL CONFIGURATION ERROR: {e}", exc_info=True)
        sys.exit(1)
    except Exception:
        logger.critical("An unexpected critical error occurred during startup.", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This print is acceptable as it's a direct user action to shut down
        print("\n[MAIN] Shutdown requested by user. Signaling orchestrator to clean up...")
        shutdown_event.set()