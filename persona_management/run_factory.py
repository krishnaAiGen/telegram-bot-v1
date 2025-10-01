# persona-management/run_factory.py

import asyncio
import json
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.syntax import Syntax
import logging  # NEW: Import logging
import time     # NEW: Import time

# Import the main pipeline orchestrator
from .pipeline import run_persona_factory_pipeline

# Rich is a great library for pretty-printing in the terminal
console = Console()

# --- NEW: JSON Logger Configuration ---
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_object = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage()
        }
        # If the message is a dict, merge it into the log object
        if isinstance(record.msg, dict):
            log_object.update(record.msg)
            log_object.pop("message", None) # Remove the redundant 'message' key
        return json.dumps(log_object)

# Configure a specific logger for LLM calls
log_handler = logging.FileHandler("llm_calls.log")
log_handler.setFormatter(JsonFormatter())

llm_logger = logging.getLogger("llm_logger")
llm_logger.setLevel(logging.INFO)
llm_logger.addHandler(log_handler)
llm_logger.propagate = False # Prevents duplicate logs in the console
# --- END NEW ---

async def test_pipeline():
    """
    An asynchronous main function to run the command-line test harness.
    """
    console.print("[bold green]--- AI Persona Management Factory ---[/bold green]")
    console.print("This tool will generate a set of AI personas based on a high-level goal.")
    
    # 1. Load the OpenAI API key from the .env file
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[bold red]CRITICAL: OPENAI_API_KEY not found in .env file. Exiting.[/bold red]")
        return

    # 2. Get the initial prompt from the user.
    try:
        initial_prompt = console.input("\n[bold]Enter your high-level goal for the bot:[/bold] ")
        if not initial_prompt:
            console.print("[bold red]Prompt cannot be empty. Exiting.[/bold red]")
            return
    except KeyboardInterrupt:
        print("\nExiting.")
        return

    # 3. Run the entire pipeline, now passing the API key.
    result = await run_persona_factory_pipeline(
        initial_prompt=initial_prompt,
        api_key=api_key
    )

    # 4. Display the final result.
    console.print("\n\n[bold green]--- PIPELINE FINAL OUTPUT ---[/bold green]")
    
    if result.get("status") == "success":
        # The prompt asks for the 'personas' key, but your pipeline returns 'characters'.
        # Let's adjust to display the correct output.
        final_output = result.get("characters", [])
        json_output = json.dumps(final_output, indent=2)
        syntax = Syntax(json_output, "json", theme="solarized-dark", line_numbers=True)
        console.print(syntax)
    else:
        console.print(f"[bold red]Pipeline failed.[/bold red]")
        console.print(f"Reason: {result.get('reason', 'Unknown error.')}")

if __name__ == "__main__":
    """
    Entry point for the script.
    """
    try:
        asyncio.run(test_pipeline())
    except KeyboardInterrupt:
        print("\n[main] Keyboard interrupt detected. Shutting down.")