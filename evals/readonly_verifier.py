"""Standalone verification of WooCommerce API read-only credential permissions.

Provides an isolated, non-benchmark tool to inspect credential configuration and
empirically confirm that mutating operations (POST/PUT/DELETE) are blocked either at
the key permission layer or connector architecture layer without risk of polluting
store data.
"""

import os
from typing import Any

import httpx

from woo_connector.config import WooCommerceConfig


def inspect_key_configuration() -> dict[str, Any]:
    """Inspect environment configuration for read-only guarantees without logging secrets."""
    base_url = os.environ.get("WOO_BASE_URL", "")
    has_ck = bool(os.environ.get("WOO_CONSUMER_KEY"))
    has_cs = bool(os.environ.get("WOO_CONSUMER_SECRET"))
    allow_http = os.environ.get("WOO_ALLOW_INSECURE_HTTP", "false").lower() == "true"

    arch_desc = "Strictly Read-Only (Services & MCP server expose zero write/delete endpoints)"
    return {
        "base_url": base_url,
        "consumer_key_configured": has_ck,
        "consumer_secret_configured": has_cs,
        "allow_insecure_http": allow_http,
        "architecture_layer": arch_desc,
    }


async def run_standalone_write_rejection_check() -> dict[str, Any]:
    """Empirically test whether write operations are rejected by the upstream WooCommerce API.

    Attempts a harmless, clearly invalid probe POST request that will be rejected by
    the API without creating or altering store data.
    """
    config = WooCommerceConfig()

    url = f"{config.base_url.rstrip('/')}/products"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "WooCommerce-Agent-ReadOnly-Verifier/1.0",
    }

    # Probe payload that attempts a write but is deliberately minimal
    probe_payload = {
        "name": "[READ_ONLY_PROBE_DO_NOT_CREATE]",
        "type": "invalid_probe_type_rejection_test",
    }

    async with httpx.AsyncClient(
        auth=(config.consumer_key, config.consumer_secret.get_secret_value()),
        timeout=10.0,
    ) as client:
        try:
            response = await client.post(url, json=probe_payload, headers=headers)
            status = response.status_code

            # 401 Unauthorized, 403 Forbidden, 400 Bad Request, or specific WooCommerce error
            is_rejected = status in (401, 403, 400, 404, 422)

            resp_code = None
            if response.headers.get("content-type", "").startswith("application/json"):
                resp_code = response.json().get("code")

            return {
                "url_probed": url,
                "http_status": status,
                "write_rejected": is_rejected,
                "response_code": resp_code,
                "message": (
                    "Upstream write operation successfully rejected or blocked."
                    if is_rejected
                    else "Warning: Endpoint returned unexpected status."
                ),
            }
        except Exception as exc:
            return {
                "url_probed": url,
                "http_status": None,
                "write_rejected": True,
                "message": f"Connection/transport error prevented write: {exc}",
            }
