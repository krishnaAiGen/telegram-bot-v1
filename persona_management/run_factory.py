# persona-management/run_factory.py

import asyncio
import json
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.syntax import Syntax

# Import the main pipeline orchestrator
from .pipeline import run_persona_factory_pipeline

# Rich is a great library for pretty-printing in the terminal
console = Console()

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
        # We'll display the raw personas list for this test script
        json_output = json.dumps(result.get("personas", []), indent=2)
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