"""Benchmark reporting engine: JSON artifact serialization and formatted Markdown tables."""

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_demo.agent import DEFAULT_SYSTEM_PROMPT
from evals.graders import TrialGrade
from evals.scenarios import EvalScenario


def get_git_commit_hash() -> str:
    """Retrieve the current HEAD git commit hash, or 'uncommitted' if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "uncommitted"


def get_system_prompt_sha256(system_prompt: str | None = None) -> str:
    """Calculate deterministic SHA-256 hash of the system prompt."""
    prompt = system_prompt if system_prompt is not None else DEFAULT_SYSTEM_PROMPT
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class BenchmarkReporter:
    """Formats and exports benchmark evaluation runs."""

    @staticmethod
    def generate_json_report(
        suite_results: dict[int | str, list[TrialGrade]],
        scenarios: list[EvalScenario],
        model: str,
        output_dir: str = "evals/results",
        system_prompt: str | None = None,
        suite_name: str | None = None,
    ) -> str:
        """Write detailed machine-readable JSON results to disk with cryptographic provenance."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"eval_run_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)

        scenario_map = {s.id: s for s in scenarios}
        total_trials = sum(len(trials) for trials in suite_results.values())
        passed_trials = sum(sum(1 for t in trials if t.passed) for trials in suite_results.values())

        git_hash = get_git_commit_hash()
        prompt_hash = get_system_prompt_sha256(system_prompt)

        data: dict[str, Any] = {
            "metadata": {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "git_commit_hash": git_hash,
                "system_prompt_sha256": prompt_hash,
                "model": model,
                "suite": suite_name or "development",
                "suite_version": "1.1",
                "total_scenarios": len(scenarios),
                "total_trials": total_trials,
                "passed_trials": passed_trials,
                "pass_rate_pct": round(
                    (passed_trials / total_trials * 100) if total_trials else 0, 1
                ),
            },
            "scenarios": [],
        }

        for sc_id, trials in suite_results.items():
            sc = scenario_map.get(sc_id)
            sc_name = sc.name if sc else f"scenario_{sc_id}"
            sc_category = sc.category if sc else "Unknown"

            sc_data: dict[str, Any] = {
                "id": sc_id,
                "name": sc_name,
                "category": sc_category,
                "prompt": sc.user_prompt if sc else "",
                "trials_count": len(trials),
                "passed_count": sum(1 for t in trials if t.passed),
                "pass_rate": round(sum(1 for t in trials if t.passed) / len(trials), 2)
                if trials
                else 0,
                "trials": [],
            }

            for t in trials:
                sc_data["trials"].append(
                    {
                        "trial_index": t.trial_index,
                        "passed": t.passed,
                        "score": t.score,
                        "duration_seconds": t.duration_seconds,
                        "tool_trace": {
                            "passed": t.tool_trace_grade.passed,
                            "tools_called": t.tool_trace_grade.tool_names_called,
                            "reasons": t.tool_trace_grade.reasons,
                        },
                        "grounding": {
                            "passed": t.grounding_grade.passed,
                            "direct_passed": t.grounding_grade.direct_entities_passed,
                            "derived_passed": t.grounding_grade.derived_entities_passed,
                            "missing_direct": t.grounding_grade.missing_direct_entities,
                            "derived_results": t.grounding_grade.derived_results,
                            "reasons": t.grounding_grade.reasons,
                        },
                        "negative_constraints": {
                            "passed": t.negative_constraint_grade.passed,
                            "forbidden_clean": t.negative_constraint_grade.forbidden_clean,
                            "concepts_present": t.negative_constraint_grade.concepts_present,
                            "forbidden_found": t.negative_constraint_grade.forbidden_found,
                            "reasons": t.negative_constraint_grade.reasons,
                        },
                        "final_answer": t.final_answer,
                        "error": t.error,
                    }
                )

            data["scenarios"].append(sc_data)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return filepath

    @staticmethod
    def generate_markdown_summary(
        suite_results: dict[int | str, list[TrialGrade]],
        scenarios: list[EvalScenario],
        model: str,
    ) -> str:
        """Render a formatted Markdown benchmark summary table."""
        scenario_map = {s.id: s for s in scenarios}
        total_trials = sum(len(trials) for trials in suite_results.values())
        passed_trials = sum(sum(1 for t in trials if t.passed) for trials in suite_results.values())
        pass_rate = (passed_trials / total_trials * 100) if total_trials else 0

        lines: list[str] = [
            "# WooCommerce MCP Agent Evaluation Report",
            "",
            f"- **Model**: `{model}`",
            f"- **Timestamp (UTC)**: `{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}`",
            f"- **Total Scenarios**: {len(scenarios)}",
            f"- **Total Trial Runs**: {total_trials}",
            f"- **Overall Pass Rate**: **{passed_trials}/{total_trials} ({pass_rate:.1f}%)**",
            "",
            "## Scenario Results",
            "",
            "| ID | Scenario | Category | Trials Pass | Tools Called | Avg Latency | Status |",
            "|---:|:---------|:---------|:-----------:|:-------------|:-----------:|:------:|",
        ]

        def _sort_key(k: int | str) -> tuple[int, str]:
            # Numeric keys sort first in integer order; string keys like 'H1' sort second
            if isinstance(k, int):
                return (0, f"{k:04d}")
            if str(k).isdigit():
                return (0, f"{int(k):04d}")
            return (1, str(k))

        for sc_id, trials in sorted(suite_results.items(), key=lambda x: _sort_key(x[0])):
            sc = scenario_map.get(sc_id)
            name = sc.name if sc else f"Scenario {sc_id}"
            cat = sc.category if sc else "Unknown"
            sc_passed = sum(1 for t in trials if t.passed)
            sc_total = len(trials)
            status_emoji = (
                "✅ PASS"
                if sc_passed == sc_total
                else ("⚠️ PARTIAL" if sc_passed > 0 else "❌ FAIL")
            )

            # Collect tools called across trials
            all_tools: set[str] = set()
            total_dur = 0.0
            for t in trials:
                all_tools.update(t.tool_trace_grade.tool_names_called)
                total_dur += t.duration_seconds

            tools_str = ", ".join(f"`{t}`" for t in sorted(all_tools)) if all_tools else "*(none)*"
            avg_lat = (total_dur / sc_total) if sc_total else 0.0

            row = (
                f"| {sc_id} | **{name}** | {cat} | {sc_passed}/{sc_total} | "
                f"{tools_str} | {avg_lat:.2f}s | {status_emoji} |"
            )
            lines.append(row)

        lines.append("")
        lines.append("## Diagnostic Observations & Failure Log")
        lines.append("")

        failures_logged = False
        for sc_id, trials in sorted(suite_results.items(), key=lambda x: _sort_key(x[0])):
            sc_failures = [t for t in trials if not t.passed]
            if sc_failures:
                failures_logged = True
                sc = scenario_map.get(sc_id)
                lines.append(f"### Scenario {sc_id}: {sc.name if sc else ''}")
                for f in sc_failures:
                    lines.append(
                        f"- **Trial {f.trial_index}**: {f.error or 'Grading check failed'}"
                    )
                    if f.tool_trace_grade.reasons:
                        tr_reasons = ", ".join(f.tool_trace_grade.reasons)
                        lines.append(f"  - *Trace Issues*: {tr_reasons}")
                    if f.grounding_grade.reasons:
                        gr_reasons = ", ".join(f.grounding_grade.reasons)
                        lines.append(f"  - *Grounding Issues*: {gr_reasons}")
                    if f.negative_constraint_grade.reasons:
                        nc_reasons = ", ".join(f.negative_constraint_grade.reasons)
                        lines.append(f"  - *Constraint Issues*: {nc_reasons}")

        if not failures_logged:
            lines.append(
                f"All {total_trials} trials passed all verification checks with 100% precision."
            )

        return "\n".join(lines)
