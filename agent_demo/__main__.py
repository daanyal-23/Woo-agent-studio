"""Command-line entry point for the Groq + WooCommerce MCP Agent Demo.

Usage:
    python -m agent_demo                  # Runs all 4 predefined scenarios
    python -m agent_demo --scenario A     # Runs Scenario A only
    python -m agent_demo --interactive    # Starts an interactive question session
    python -m agent_demo --prompt "..."   # Runs a single custom question
"""

import argparse
import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:
    pass

from groq import Groq

from agent_demo.agent import run_agent_turn
from agent_demo.client import connect_mcp_client
from agent_demo.scenarios import SCENARIOS


def check_required_env() -> bool:
    """Validate that required environment variables are present without printing secrets."""
    missing: list[str] = []
    if not os.environ.get("GROQ_API_KEY"):
        missing.append("GROQ_API_KEY")
    if not os.environ.get("WOO_BASE_URL"):
        missing.append("WOO_BASE_URL")
    if not os.environ.get("WOO_CONSUMER_KEY"):
        missing.append("WOO_CONSUMER_KEY")
    if not os.environ.get("WOO_CONSUMER_SECRET"):
        missing.append("WOO_CONSUMER_SECRET")

    if missing:
        sys.stderr.write(
            f"Error: Missing required environment variable(s): {', '.join(missing)}\n"
            "Please export these variables before running the demo.\n"
        )
        return False
    return True


async def run_scenario_suite(scenario_keys: list[str]) -> None:
    """Run specified scenarios sequentially through the real MCP server and Groq."""
    groq_client = Groq()

    print("\n" + "=" * 70)
    print("STARTING GROQ + WOOCOMMERCE MCP AGENT DEMO")
    print(f"Selected Scenarios: {', '.join(scenario_keys)}")
    print("=" * 70)

    async with connect_mcp_client() as mcp_client:
        print(f"Connected to MCP Server. Discovered {len(mcp_client.tools)} tools:")
        for t in mcp_client.tools:
            print(f"  - {t.name}")

        for key in scenario_keys:
            scenario = SCENARIOS.get(key)
            if not scenario:
                print(f"Unknown scenario key: {key}")
                continue

            print(f"\n>>> Running {scenario.title}")
            print(f"Description: {scenario.description}")

            await run_agent_turn(
                user_prompt=scenario.prompt,
                mcp_client=mcp_client,
                groq_client=groq_client,
            )


async def run_interactive_mode() -> None:
    """Run an interactive prompt session with the agent."""
    groq_client = Groq()

    async with connect_mcp_client() as mcp_client:
        print("\n" + "=" * 70)
        print("GROQ + WOOCOMMERCE MCP INTERACTIVE AGENT")
        print("Type your questions below. Enter 'exit' or 'quit' to end.")
        print("=" * 70)

        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting interactive session.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            await run_agent_turn(
                user_prompt=user_input,
                mcp_client=mcp_client,
                groq_client=groq_client,
            )


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Run the Groq + WooCommerce MCP Agent Demo.")
    parser.add_argument(
        "--scenario",
        choices=["A", "B", "C", "D"],
        help="Run a specific scenario (A, B, C, or D).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start an interactive session.",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="Ask a custom single question.",
    )

    args = parser.parse_args()

    if not check_required_env():
        return 1

    if args.interactive:
        await run_interactive_mode()
    elif args.prompt:
        groq_client = Groq()
        async with connect_mcp_client() as mcp_client:
            await run_agent_turn(
                user_prompt=args.prompt,
                mcp_client=mcp_client,
                groq_client=groq_client,
            )
    elif args.scenario:
        await run_scenario_suite([args.scenario])
    else:
        # Default: run all 4 scenarios
        await run_scenario_suite(["A", "B", "C", "D"])

    return 0


def main() -> None:
    try:
        sys.exit(asyncio.run(main_async()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
