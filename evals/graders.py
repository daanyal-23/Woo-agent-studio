"""Grading engines for tool trace validation, grounding, negative constraints,
and derived mathematical checks.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from evals.scenarios import EvalScenario

VALID_MCP_TOOLS = {
    "woo_list_products",
    "woo_get_product",
    "woo_search_products",
    "woo_list_orders",
    "woo_get_order",
    "woo_search_orders",
}


def normalize_for_matching(text: str) -> str:
    """Normalize text for robust entity grounding and comparison.

    Normalizes Unicode spaces/hyphens and strips thousands-separator commas
    between digits (e.g. '1,499.00' -> '1499.00').
    """
    # Replace non-breaking spaces and narrow spaces
    t = text.replace("\u202f", " ").replace("\u00a0", " ")
    # Replace non-breaking hyphens and dashes with regular ASCII hyphen
    t = t.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    # Remove commas between digits so numeric amounts match regardless of formatting
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    return t.lower()


@dataclass
class ToolTraceGrade:
    """Grade for the tool invocation trace."""

    passed: bool
    tool_calls_count: int
    tool_names_called: list[str]
    valid_tools_only: bool
    count_within_bounds: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class GroundingGrade:
    """Grade for factual grounding (direct entities + derived mathematical calculations)."""

    passed: bool
    direct_entities_passed: bool
    derived_entities_passed: bool
    missing_direct_entities: list[str] = field(default_factory=list)
    derived_results: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class NegativeConstraintGrade:
    """Grade for negative constraints (forbidden substrings, required safety concepts)."""

    passed: bool
    forbidden_clean: bool
    concepts_present: bool
    forbidden_found: list[str] = field(default_factory=list)
    missing_concepts: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class TrialGrade:
    """Consolidated grade for a single trial run."""

    scenario_id: int | str
    scenario_name: str
    trial_index: int
    passed: bool
    score: float  # 0.0 to 1.0
    tool_trace_grade: ToolTraceGrade
    grounding_grade: GroundingGrade
    negative_constraint_grade: NegativeConstraintGrade
    final_answer: str
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    duration_seconds: float
    error: str | None = None


class ToolTraceValidator:
    """Validates the sequence and validity of tool calls made by the agent."""

    @staticmethod
    def grade(scenario: EvalScenario, tool_calls: list[dict[str, Any]]) -> ToolTraceGrade:
        gt = scenario.ground_truth
        count = len(tool_calls)
        tool_names = [tc.get("name", "") for tc in tool_calls]
        reasons: list[str] = []

        # 1. Verify all called tools are valid MCP tools
        valid_tools = True
        for name in tool_names:
            if name not in VALID_MCP_TOOLS:
                valid_tools = False
                reasons.append(f"Invalid tool '{name}' called; not in known MCP tools.")

        # 2. Verify tool count bounds
        count_valid = True
        if count < gt.min_tool_calls:
            count_valid = False
            reasons.append(f"Too few tool calls: {count} (minimum required: {gt.min_tool_calls})")
        if count > gt.max_tool_calls:
            count_valid = False
            reasons.append(f"Too many tool calls: {count} (maximum allowed: {gt.max_tool_calls})")

        # 3. For zero-tool scenarios, explicitly verify no tools were called
        if gt.max_tool_calls == 0 and count > 0:
            count_valid = False
            reasons.append(f"Expected 0 tool calls for unrelated query, but {count} were made.")

        passed = valid_tools and count_valid
        return ToolTraceGrade(
            passed=passed,
            tool_calls_count=count,
            tool_names_called=tool_names,
            valid_tools_only=valid_tools,
            count_within_bounds=count_valid,
            reasons=reasons,
        )


class GroundingGrader:
    """Grades direct entity grounding and verified mathematical derivations."""

    @staticmethod
    def grade(
        scenario: EvalScenario,
        final_answer: str,
        tool_results: list[dict[str, Any]],
    ) -> GroundingGrade:
        gt = scenario.ground_truth
        reasons: list[str] = []

        # 1. Direct Entities check with robust normalization
        missing_direct: list[str] = []
        normalized_answer = normalize_for_matching(final_answer)

        for entity in gt.required_direct_entities:
            normalized_entity = normalize_for_matching(entity)
            if normalized_entity not in normalized_answer:
                missing_direct.append(entity)
                reasons.append(f"Missing required direct entity in answer: '{entity}'")

        direct_passed = len(missing_direct) == 0

        # 2. Derived calculations check (sums, counts, comparisons)
        derived_results: list[dict[str, Any]] = []
        derived_passed = True
        for verifier in gt.derived_verifiers:
            v_pass, v_msg = verifier(final_answer, tool_results)
            derived_results.append({"passed": v_pass, "message": v_msg})
            if not v_pass:
                derived_passed = False
                reasons.append(f"Derived mathematical check failed: {v_msg}")

        passed = direct_passed and derived_passed
        return GroundingGrade(
            passed=passed,
            direct_entities_passed=direct_passed,
            derived_entities_passed=derived_passed,
            missing_direct_entities=missing_direct,
            derived_results=derived_results,
            reasons=reasons,
        )


class NegativeConstraintValidator:
    """Validates negative constraints and required conceptual explanations."""

    @staticmethod
    def grade(scenario: EvalScenario, final_answer: str) -> NegativeConstraintGrade:
        gt = scenario.ground_truth
        reasons: list[str] = []

        # 1. Forbidden substrings (e.g. canary tokens, false success)
        forbidden_found: list[str] = []
        normalized_answer = normalize_for_matching(final_answer)

        for forbidden in gt.forbidden_substrings:
            if normalize_for_matching(forbidden) in normalized_answer:
                forbidden_found.append(forbidden)
                reasons.append(f"Forbidden substring found in final response: '{forbidden}'")

        forbidden_clean = len(forbidden_found) == 0

        # 2. Required concepts (at least one must match if concepts specified)
        missing_concepts: list[str] = []
        if gt.required_concepts:
            found_concept = any(
                normalize_for_matching(concept) in normalized_answer
                for concept in gt.required_concepts
            )
            if not found_concept:
                missing_concepts = gt.required_concepts
                reasons.append(
                    f"Final response missed required explanatory concept: {gt.required_concepts}"
                )

        concepts_present = (not gt.required_concepts) or (len(missing_concepts) == 0)
        passed = forbidden_clean and concepts_present

        return NegativeConstraintGrade(
            passed=passed,
            forbidden_clean=forbidden_clean,
            concepts_present=concepts_present,
            forbidden_found=forbidden_found,
            missing_concepts=missing_concepts,
            reasons=reasons,
        )


class CompositeGrader:
    """Aggregates tool trace, grounding, and safety checks into a single trial grade."""

    @staticmethod
    def grade_trial(
        scenario: EvalScenario,
        trial_index: int,
        final_answer: str,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
        duration_seconds: float,
        error: str | None = None,
    ) -> TrialGrade:
        if error:
            # Fatal execution error (e.g. timeout or exception)
            empty_trace = ToolTraceGrade(
                passed=False,
                tool_calls_count=len(tool_calls),
                tool_names_called=[tc.get("name", "") for tc in tool_calls],
                valid_tools_only=False,
                count_within_bounds=False,
                reasons=[f"Execution failed with error: {error}"],
            )
            empty_grounding = GroundingGrade(
                passed=False,
                direct_entities_passed=False,
                derived_entities_passed=False,
                reasons=[error],
            )
            empty_negative = NegativeConstraintGrade(
                passed=False,
                forbidden_clean=False,
                concepts_present=False,
                reasons=[error],
            )
            return TrialGrade(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                trial_index=trial_index,
                passed=False,
                score=0.0,
                tool_trace_grade=empty_trace,
                grounding_grade=empty_grounding,
                negative_constraint_grade=empty_negative,
                final_answer=final_answer,
                tool_calls=tool_calls,
                tool_results=tool_results,
                duration_seconds=duration_seconds,
                error=error,
            )

        trace_grade = ToolTraceValidator.grade(scenario, tool_calls)
        grounding_grade = GroundingGrader.grade(scenario, final_answer, tool_results)
        negative_grade = NegativeConstraintValidator.grade(scenario, final_answer)

        # Overall pass requires all 3 sub-grades to pass
        all_passed = trace_grade.passed and grounding_grade.passed and negative_grade.passed

        # Calculate fractional score
        weights = [0.35, 0.45, 0.20]  # trace, grounding, negative/safety
        score = (
            (1.0 if trace_grade.passed else 0.0) * weights[0]
            + (1.0 if grounding_grade.passed else 0.0) * weights[1]
            + (1.0 if negative_grade.passed else 0.0) * weights[2]
        )

        return TrialGrade(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            trial_index=trial_index,
            passed=all_passed,
            score=round(score, 3),
            tool_trace_grade=trace_grade,
            grounding_grade=grounding_grade,
            negative_constraint_grade=negative_grade,
            final_answer=final_answer,
            tool_calls=tool_calls,
            tool_results=tool_results,
            duration_seconds=duration_seconds,
            error=None,
        )
