# WooCommerce Connector Capabilities

## Overview

The WooCommerce Private Connector is a read-only Model Context Protocol (MCP) service providing AI agents and LLM hosts with secure, structured access to merchant catalog and order data. It wraps the WooCommerce REST API (v3) with strict input validation, PII masking, deterministic pagination, resilient retries, and typed domain schemas.

## Architecture

```
LLM / MCP Host
  → MCP stdio server (mcp_server.py)
    → ProductService / OrderService (products.py, orders.py)
      → WooCommerceClient (client.py)
        → WooCommerce REST API (/wp-json/wc/v3)
```

The underlying services (`ProductService` and `OrderService`) remain the single source of truth for business logic, pagination contracts, input validation, and domain modeling. The MCP server layer is a thin adapter over these services: it manages a single shared `WooCommerceClient` lifecycle, registers tool definitions, and translates internal domain exceptions into structured MCP error results without maintaining independent HTTP clients or WooCommerce-specific logic.

## Available MCP Tools

The connector exposes exactly six read-only MCP tools:

### `woo_list_products`
- **Purpose**: List catalog products with status filtering and pagination.
- **Parameters**:
  - `page` (`int`, default: `1`): 1-indexed page number (must be $\ge 1$).
  - `per_page` (`int`, default: `10`): Number of items per page (range: `1`–`100`).
  - `status` (`ProductStatus | None` (`Literal["publish", "draft", "pending", "private"] | None`), default: `None`): Product status filter.
- **Returns**: `PaginatedResult[Product]` containing items and pagination metadata.
- **Limitations**: Does not filter by categories or tags at the tool level.

### `woo_get_product`
- **Purpose**: Retrieve a single product by its integer ID.
- **Parameters**:
  - `product_id` (`int`): Unique product ID (must be $\ge 1$).
- **Returns**: `Product` domain model.
- **Limitations**: Returns `NOT_FOUND` error if the ID does not exist.

### `woo_search_products`
- **Purpose**: Search catalog products by text query.
- **Parameters**:
  - `query` (`str`): Non-empty search term.
  - `page` (`int`, default: `1`): 1-indexed page number (must be $\ge 1$).
  - `per_page` (`int`, default: `10`): Items per page (range: `1`–`100`).
  - `status` (`ProductStatus | None` (`Literal["publish", "draft", "pending", "private"] | None`), default: `None`): Product status filter.
- **Returns**: `PaginatedResult[Product]`.
- **Limitations**: Governed by native WooCommerce keyword search semantics.

### `woo_list_orders`
- **Purpose**: List merchant orders with status filtering and pagination.
- **Parameters**:
  - `page` (`int`, default: `1`): 1-indexed page number (must be $\ge 1$).
  - `per_page` (`int`, default: `10`): Items per page (range: `1`–`100`).
  - `status` (`OrderStatus | None` (`Literal["pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"] | None`), default: `None`): Order status filter.
- **Returns**: `PaginatedResult[Order]`.
- **Limitations**: Returns PII-minimized order representations.

### `woo_get_order`
- **Purpose**: Retrieve a single order by its integer ID.
- **Parameters**:
  - `order_id` (`int`): Unique order ID (must be $\ge 1$).
- **Returns**: `Order` domain model.
- **Limitations**: Returns `NOT_FOUND` error if the ID does not exist.

### `woo_search_orders`
- **Purpose**: Search orders by text query.
- **Parameters**:
  - `query` (`str`): Non-empty search term.
  - `page` (`int`, default: `1`): 1-indexed page number (must be $\ge 1$).
  - `per_page` (`int`, default: `10`): Items per page (range: `1`–`100`).
  - `status` (`OrderStatus | None` (`Literal["pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"] | None`), default: `None`): Order status filter.
- **Returns**: `PaginatedResult[Order]`.
- **Limitations**: Governed by native WooCommerce keyword search semantics.

> **Service-Level Only Method**: `get_product_by_sku` exists on `ProductService` for exact SKU lookup, but is deliberately not exposed as an MCP tool to keep the agent tool surface minimal and unambiguous.

## Search Semantics

Keyword search via WooCommerce's native `search` parameter. Not semantic or fuzzy. Which fields match is not guaranteed.

The connector does not make claims regarding SQL matching, full-text ranking, or specific title/description field indexing.

### Verified Real-Store Observations
In testing against the seeded local WooCommerce environment, the native `search` parameter produced the following verified behaviors:
- `orders?search=Merchant` → returned 6 orders (`X-WP-Total: 6`); matched field not determined by API guarantee.
- `orders?search=30` → returned order ID `30` (`X-WP-Total: 1`).
- `orders?search=pay_det_012_multi_item` → matched order `30`, where `pay_det_012_multi_item` was the payment transaction ID (`X-WP-Total: 1`).

These observations confirm that WooCommerce's search parameter matches against certain seeded fields in practice, but they do not constitute an API guarantee across all field types, versions, or WordPress installations.

## Pagination

Pagination is deterministic and exposed through the immutable `PaginatedResult[T]` container:
- `items`: List of models (`Product` or `Order`).
- `page`: Requested page number ($\ge 1$).
- `per_page`: Requested items per page (allowed bounds: `1`–`100`).
- `total_count`: Total number of matching records (integer or `None`).
- `total_pages`: Total number of pages available (integer or `None`).
- `has_more`: Boolean indicating whether subsequent pages exist.
- `next_page`: Next page number (`page + 1`) if `has_more` is `True`, otherwise `None`.

### Header Derivation & Fallback Contract
Pagination metadata is parsed directly from WooCommerce HTTP response headers:
- `X-WP-Total` $\to$ `total_count`
- `X-WP-TotalPages` $\to$ `total_pages`
- If `X-WP-TotalPages` is present: `has_more = page < total_pages` and `next_page = page + 1 if has_more else None`.
- If pagination headers are missing: `has_more = False` and `next_page = None`. The connector never infers `has_more = True` simply because `len(items) == per_page`.

## Order Data & PII Minimization

Order models apply strict PII minimization to protect customer privacy:
- **Exposed**: Customer name (`customer_name`) is exposed for order identification.
- **Masked**: Email addresses are masked before exposure.
- **Omitted**: Phone numbers, billing addresses, and customer notes are completely omitted from models.
- **Financial Audit Fields**: The `Order` model exposes key transaction metadata:
  - `payment_method`: Gateway identifier (e.g. `"bacs"`, `"cod"`).
  - `payment_method_title`: Gateway display title.
  - `transaction_id`: Payment gateway transaction reference.
  - `date_paid`: Payment timestamp.
  - `refund_total`: Aggregated monetary refund total.
- **Itemized Refunds**: Itemized refund line entries are not currently exposed.

## Retry & Error Behavior

The HTTP client includes automatic retries with exponential backoff and jitter for transient failures:
- **Retryable Conditions**: HTTP `429` (Rate Limit Exceeded), HTTP `5xx` (500, 502, 503, 504), transient connection errors, and request timeouts.
- **Retry-After**: Automatically respects the `Retry-After` header when provided by WooCommerce or reverse proxies.
- **Non-Retryable Conditions**: Client errors (`400`, `401`, `403`, `404`) fail immediately without retry.

### Structured MCP Error Codes
Tool failures return `CallToolResult(is_error=True)` with structured JSON payloads containing uppercase error codes:
- `INVALID_INPUT`: Out-of-bounds pagination (`page < 1`, `per_page < 1` or `> 100`), empty search queries, or invalid status filters.
- `NOT_FOUND`: Requested product or order ID does not exist.
- `UNEXPECTED_RESPONSE`: Upstream response returned malformed JSON or unparseable schema.
- `AUTHENTICATION_FAILED`: Invalid API credentials (`401`).
- `PERMISSION_DENIED`: Insufficient API key permissions (`403`).
- `RATE_LIMIT_EXCEEDED`: Exceeded retry limits during rate limiting (`429`).
- `SERVER_ERROR`: Upstream server errors persisting after retries (`5xx`).
- `INTERNAL_ERROR`: Unexpected internal exceptions.

## Security & Prompt Injection

- **Untrusted Merchant Data**: All product names, descriptions, attributes, and order text are treated strictly as untrusted external data.
- **No Execution**: The connector never parses or executes catalog content as instructions.
- **Adversarial Test Data**: The seeded store dataset includes products with simulated prompt-injection descriptions (e.g. text attempting to override agent instructions). The connector safely returns these descriptions as raw string data without interpretation.

## Read-Only Boundary

The connector enforces an absolute read-only boundary:
- No product creation, updates, or deletions.
- No order creation, updates, or status modifications.
- No customer management tools.
- No store administration or setting tools.
- No arbitrary API passthrough or proxy endpoints.

The write-capable WooCommerce API key is restricted exclusively to the standalone seeding utility (`src/woo_connector/seed.py`) and is never loaded or accessible by the MCP server.

## Transport & Configuration

- **Transport**: Standard I/O (`stdio`).
- **Stream Discipline**: `stdout` is reserved strictly for MCP JSON-RPC protocol messages. All application logging, debug output, and error traces are routed exclusively to `stderr`.
- **TLS Assumption**: The connector assumes HTTPS in production. Plain HTTP is rejected unless `WOO_ALLOW_INSECURE_HTTP=true` is explicitly set for local development.
- **Base URL Normalization**: Accepts URLs in various formats (e.g. `http://localhost:8080`, `http://localhost:8080/`, or `http://localhost:8080/wp-json/wc/v3`) and automatically canonicalizes to a single `/wp-json/wc/v3` path without doubling.

## Running the Server

### Command Line
```bash
# Via module execution
python -m woo_connector.mcp_server

# Via console script entrypoint
woo-connector-mcp
```

### Client Configuration Example
```json
{
  "mcpServers": {
    "woocommerce": {
      "command": "<path-to-repo>\\.venv\\Scripts\\python.exe",
      "args": ["-m", "woo_connector.mcp_server"],
      "env": {
        "WOO_BASE_URL": "http://localhost:8080",
        "WOO_CONSUMER_KEY": "ck_your_consumer_key_here",
        "WOO_CONSUMER_SECRET": "cs_your_consumer_secret_here",
        "WOO_ALLOW_INSECURE_HTTP": "true"
      }
    }
  }
}
```

## Known Limitations

- **Synchronous Execution & Threading**: In `mcp 2.3.0`, FastMCP offloads synchronous tool functions to a worker thread pool via `anyio.to_thread.run_sync`. Synchronous HTTP calls and retry delays (`time.sleep`) block that worker thread servicing the call, but do **not** block the main asyncio event loop handling stdio JSON-RPC transport.
- **Search Semantics**: Search is keyword-based via WooCommerce's native `search` parameter, not semantic or fuzzy. Which fields match is not guaranteed.
- **Itemized Refunds**: Refund amounts are exposed as aggregated totals; itemized refund lines are not exposed.

## Verified Status

- **Offline Test Suite**: 119 unit, RESPX, and evaluation grader tests passing.
- **Live Integration Tests**: 5 tests skipped by default; live MCP stdio and agent demo smoke tests verified against local WooCommerce instance.
- **Code Quality**: Ruff lint clean (`ruff check .`).
- **Evaluation Benchmark**: Pre-change development benchmark achieved 36/36 passed on `openai/gpt-oss-120b` (see [docs/evaluation-history.md](evaluation-history.md), [docs/evaluation-scenarios.md](evaluation-scenarios.md), and [docs/submission-notes.md](submission-notes.md)).
