# Forward-Deployed Engineer, Agent Studio: Assignment 3 — Submission Notes

This document provides a concise technical summary of the **WooCommerce Agent Connector** for evaluators of the Forward-Deployed Engineer, Agent Studio: Assignment 3 assessment.

---

## 1. Executive Summary

This submission delivers a secure, read-only Model Context Protocol (MCP) connector and evaluation harness integrating AI agents with WooCommerce merchant stores.

```
AI Agent (Groq / Host)
   ↕ (stdio JSON-RPC / MCP Protocol)
MCP Server (mcp_server.py — exactly 6 read-only tools)
   ↕ (Domain Services)
ProductService / OrderService (products.py, orders.py)
   ↕ (Synchronous HTTP Client)
WooCommerce REST API (/wp-json/wc/v3)
```

---

## 2. Core Deliverables

### A. Private Read-Only WooCommerce Connector (`src/woo_connector/`)
- **Transport & Security**: Synchronous `httpx.Client` enforcing HTTPS by default (`WOO_ALLOW_INSECURE_HTTP=true` restricted strictly to local dev). Credentials protected via `SecretStr`.
- **Structured Error Handling**: Mapped hierarchy (`BadRequestError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `RateLimitExceededError`, `ServerError`, `ResponseParseError`) exposing `{code, message, retryable, retry_after}`.
- **Resilient Retry Policy**: Automatic retries with exponential backoff and jitter for transient 429 and 5xx errors; respects `Retry-After` headers (capped at 30s).
- **Domain Models & PII Minimization**: Customer email masked (`customer_email_masked`); raw emails, billing addresses, phone numbers, and customer notes omitted.
- **Prompt Injection Defense**: Untrusted merchant catalog descriptions are treated strictly as inert string data and never executed.

### B. FastMCP stdio Server (`woo_connector.mcp_server`)
Exposes exactly six read-only MCP tools:
1. `woo_list_products`: Catalog browsing with pagination and status filters.
2. `woo_get_product`: Single product lookup by integer ID.
3. `woo_search_products`: Native text search across catalog.
4. `woo_list_orders`: Order browsing with lifecycle status filters.
5. `woo_get_order`: Single order lookup with PII minimization.
6. `woo_search_orders`: Native text search across orders.

All tools include `readOnlyHint=True` and map internal domain exceptions to structured uppercase JSON error payloads (`INVALID_INPUT`, `NOT_FOUND`, `RATE_LIMIT_EXCEEDED`, etc.).

### C. Agent Demo (`agent_demo/`)
An agent orchestration loop using open-weight models on Groq (`openai/gpt-oss-120b`) communicating over stdio MCP with real-time tool execution and terminal observability.

### D. Multi-Dimensional Evaluation Harness (`evals/`)
A programmatic grading harness evaluating agent performance without human intervention:
- **12 Development Scenarios**: Testing catalog queries (3 plans: 13, 14, 15 + 2 add-ons: 16, 17), monetary calculations, refund detection, PII boundaries, multi-hop lookups, pagination aggregations, write rejections, zero-tool queries, prompt-injection canaries, and upstream 500 error resilience.
- **Programmatic Grading**: Orthogonal validation across `ToolTraceValidator` (allowed tools & turn limits), `NegativeConstraintValidator` (forbidden strings & canaries), and `GroundingGrader` (direct entity verification and derived mathematical checks).
- **Grader Validation Suite**: 13 automated test cases in `tests/test_grader_validation.py` asserting that the grading engines fail hallucinated data, wrong sums, leaked canaries, and invalid tool traces.

---

## 3. Key Findings & Engineering Integrity

1. **Pre-Change Development Benchmark**:
   The pre-change development suite completed **36 / 36 trials (100.0%)** on `openai/gpt-oss-120b` (`evals/results/eval_run_20261007_073636.json`). This run predates grader v2 refinements and dynamic ID resolution, and was not repeated on 120b.
2. **Capability-Boundary Discovery**:
   Testing held-out queries (such as *"Show me last week's failed orders"*) revealed that these requests require capabilities that the exposed tools do not provide natively. The evaluation agent sometimes attempted client-side inspection/filtering, but did so inconsistently and did not reliably disclose that limitation.
3. **Grader False-Positive Discovery & Fix**:
   Initial H2 testing scored 1/1 because the keyword grader matched table headers containing `"Date Created (UTC)"`. The grader was tightened to enforce semantic capability disclosure (`evals/results/eval_run_20261007_085912.json`, score 0.55), correctly catching the omission.
4. **General Prompt Experiment & Revert Rationale**:
   A general prompt addition (Rules 6 & 7) was tested on commit `082011aad3ff7d34dad8beb67e2c832da54560ae`. The keep condition (a clean 120B regression run) could not be completed, so the revision was reverted. H2 and H6 also did not improve.
5. **Shipped Prompt Evaluation Scope**:
   The shipped baseline prompt was **NOT** evaluated on H5–H7 (those results reflect the reverted experimental prompt).
6. **H7 Quota Accounting**:
   In both 120b H7 runs (`eval_run_20261007_091646.json` and `eval_run_20261007_092855.json`), the outcome was exactly 1 completed behavioral pass and 2 HTTP 429 daily-token-quota failures per run. The quota failures are not classified as behavioral failures.

---

## 4. Verification & Reproducibility

| Verification Metric | Value |
|---|---|
| **Final Baseline Commit** | `ba3da63756cee78de282fdaaad053fa291a95672` |
| **Baseline System Prompt SHA-256** | `4e1ead80a9f7e384db8d5f3f74c4b3877064c6de51f2fc9c2040af7043ced69f` |
| **Tested Experiment Prompt SHA-256** | `76e94f59cedc261958b68051b9dc7e0f910771992b638cd0bc74e7fb361e88b1` |
| **Original H2 Tightened Artifact SHA-256** | `8380c57c86a784c14912655f02829f2ac189935fe8c3f61c0879af7e9ac941d7` |
| **Unit & Integration Test Suite** | **119 passed, 5 skipped** (`pytest tests/`) |
| **Linter Status** | **Clean** (`ruff check .`) |
| **Read-Only Proof** | Tool annotations `readOnlyHint=True`; separate write credentials for seeding; MCP server has zero write endpoints; standalone write-rejection check (`python -m evals --verify-readonly-key`). |

---

## 5. Quickstart for Evaluators

```bash
# 1. Install package and dependencies
pip install -e ".[dev,demo]"

# 2. Run the offline test suite (119 unit/RESPX/grader tests)
pytest

# 3. Verify code quality
ruff check .

# 4. Verify read-only credentials via standalone probe
python -m evals --verify-readonly-key

# 5. Run the MCP server over stdio
python -m woo_connector.mcp_server

# 6. Run the agent demo (requires GROQ_API_KEY and running WooCommerce instance)
python -m agent_demo --scenario A
```
