"""CLI entry point for WooCommerce MCP agent evaluation harness."""

import argparse
import asyncio
import os
import sys

from evals.readonly_verifier import inspect_key_configuration, run_standalone_write_rejection_check
from evals.reporter import BenchmarkReporter
from evals.runner import EvalRunner
from evals.scenarios import get_scenario_by_id, get_scenarios_for_suite


def load_optional_env() -> None:
    """Safely load .env if python-dotenv is installed, without overriding existing env."""
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass


def configure_utf8_output() -> None:
    """Ensure standard output correctly prints Unicode symbols (e.g. ₹)."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


async def run_cli() -> int:
    load_optional_env()
    configure_utf8_output()

    parser = argparse.ArgumentParser(
        description="Evaluation harness for Groq + WooCommerce MCP connector."
    )
    parser.add_argument(
        "--suite",
        type=str,
        default="dev",
        choices=["dev", "heldout", "all"],
        help="Evaluation suite: 'dev' (12 dev scenarios), 'heldout' (4 held-out), or 'all'.",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Run a specific scenario ID (1-12 or H1-H4). If omitted, runs all in suite.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=3,
        help="Number of trials per scenario (default: 3).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Groq model to evaluate (default: from env or openai/gpt-oss-120b).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose turn-by-turn tool executions during evaluation.",
    )
    parser.add_argument(
        "--verify-readonly-key",
        action="store_true",
        help="Run standalone safe verification of read-only key permissions and exit.",
    )

    args = parser.parse_args()

    # Handle standalone read-only verification
    if args.verify_readonly_key:
        print("\n" + "=" * 65)
        print("STANDALONE READ-ONLY CREDENTIAL VERIFICATION")
        print("=" * 65)
        info = inspect_key_configuration()
        print(f"Base URL: {info['base_url']}")
        print(f"Consumer Key Configured: {info['consumer_key_configured']}")
        print(f"Consumer Secret Configured: {info['consumer_secret_configured']}")
        print(f"Architecture: {info['architecture_layer']}")

        print("\nExecuting safe write-rejection probe (harmless minimal invalid POST)...")
        probe_res = await run_standalone_write_rejection_check()
        print(f"Probe URL: {probe_res['url_probed']}")
        print(f"HTTP Status: {probe_res['http_status']}")
        print(f"Write Rejected: {probe_res['write_rejected']}")
        print(f"Result: {probe_res['message']}")
        print("=" * 65 + "\n")
        return 0

    # Ensure GROQ_API_KEY is present
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        print(
            "Error: GROQ_API_KEY environment variable is not set. "
            "Please configure GROQ_API_KEY in the environment or .env.",
            file=sys.stderr,
        )
        return 1

    from groq import Groq

    from agent_demo.client import connect_mcp_client
    from evals.fixtures import resolve_store_fixtures

    groq_client = Groq(api_key=groq_api_key)

    eval_runner = EvalRunner(
        groq_client=groq_client,
        model=args.model,
    )

    # Connect live MCP client, resolve store fixtures dynamically, and execute scenarios
    async with connect_mcp_client() as live_client:
        try:
            fixtures = await resolve_store_fixtures(live_client)
        except Exception as exc:
            msg = f"Store Fixture Warning: {exc}. Falling back to default fixtures."
            print(msg, file=sys.stderr)
            from evals.fixtures import DEFAULT_OFFLINE_FIXTURES

            fixtures = DEFAULT_OFFLINE_FIXTURES

        # Select scenarios based on CLI arguments and resolved fixtures
        if args.scenario is not None:
            sc = get_scenario_by_id(args.scenario, fixtures=fixtures)
            if not sc:
                print(f"Error: Scenario ID '{args.scenario}' not found.")
                return 1
            scenarios_to_run = [sc]
        else:
            scenarios_to_run = get_scenarios_for_suite(args.suite, fixtures=fixtures)

        print("\n" + "=" * 70)
        sc_cnt = len(scenarios_to_run)
        suite_label = (
            f"Suite: {args.suite.upper()}"
            if args.scenario is None
            else f"Scenario: {args.scenario}"
        )
        print(
            f"STARTING EVALUATION BENCHMARK ({suite_label}, {sc_cnt} scenarios, "
            f"{args.trials} trial(s) each)"
        )
        print(f"Model: {eval_runner.model}")
        print("=" * 70 + "\n")

        suite_results: dict[int | str, list] = {}
        for sc in scenarios_to_run:
            trials = await eval_runner.run_scenario_benchmark(
                scenario=sc,
                num_trials=args.trials,
                live_mcp_client=live_client,
                verbose=args.verbose,
            )
            suite_results[sc.id] = trials

    # Export machine-readable JSON
    json_path = BenchmarkReporter.generate_json_report(
        suite_results=suite_results,
        scenarios=scenarios_to_run,
        model=eval_runner.model,
        suite_name=args.suite if args.scenario is None else f"scenario_{args.scenario}",
    )

    # Render Markdown table
    md_summary = BenchmarkReporter.generate_markdown_summary(
        suite_results=suite_results,
        scenarios=scenarios_to_run,
        model=eval_runner.model,
    )

    print("\n" + md_summary)
    print(f"\nArtifact saved to: {json_path}\n")

    # Return non-zero exit code if any trial failed
    all_passed = all(all(t.passed for t in trials) for trials in suite_results.values())
    return 0 if all_passed else 1


def main() -> None:
    exit_code = asyncio.run(run_cli())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
