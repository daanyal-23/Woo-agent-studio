"""Store fixture resolver to decouple evaluations from hardcoded auto-increment WooCommerce IDs.

Resolves live product IDs and order IDs dynamically by matching invariant seeded
identifiers (product SKUs, order transaction IDs, and order _seed_id meta keys).
"""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResolvedStoreFixtures:
    """Store-aware registry mapping invariant seed keys to actual WooCommerce numeric IDs."""

    # Product SKU -> WooCommerce product numeric ID
    products_by_sku: dict[str, int] = field(default_factory=dict)

    # Order transaction_id -> WooCommerce order numeric ID
    orders_by_tx_id: dict[str, int] = field(default_factory=dict)

    # Order seed_id -> WooCommerce order numeric ID
    orders_by_seed_id: dict[str, int] = field(default_factory=dict)


# Default offline fixtures used for unit testing without a live WooCommerce store connection
DEFAULT_OFFLINE_FIXTURES = ResolvedStoreFixtures(
    products_by_sku={
        "PROD-STARTER-PLAN": 13,
        "PROD-MERCHANT-PRO": 14,
        "PROD-PREMIUM-ANNUAL": 15,
        "PROD-GATEWAY-ADDON": 16,
        "PROD-ENTERPRISE-SUPPORT": 17,
    },
    orders_by_tx_id={
        "pay_det_001_completed": 18,
        "pay_fail_004_insufficient_funds": 21,
        "pay_det_005_refunded": 22,
        "pay_det_007_partial_refund": 25,
        "pay_det_009_enterprise_sub": 27,
        "pay_fail_011_otp_timeout": 29,
        "pay_det_012_multi_item": 30,
    },
    orders_by_seed_id={
        "seed_order_001": 18,
        "seed_order_004": 21,
        "seed_order_005": 22,
        "seed_order_007": 25,
        "seed_order_009": 27,
        "seed_order_011": 29,
        "seed_order_012": 30,
    },
)


async def resolve_store_fixtures(mcp_client: Any) -> ResolvedStoreFixtures:
    """Query WooCommerce through MCP tools to resolve actual numeric IDs for seeded fixtures.

    Raises:
        RuntimeError: If mandatory seeded products or orders cannot be found.
    """
    fixtures = ResolvedStoreFixtures()

    # 1. Resolve Products
    try:
        prod_res_raw = await mcp_client.call_tool("woo_list_products", {"page": 1, "per_page": 100})
        prod_data = json.loads(prod_res_raw) if isinstance(prod_res_raw, str) else prod_res_raw
        items = prod_data.get("items", []) if isinstance(prod_data, dict) else []
        for item in items:
            sku = item.get("sku")
            p_id = item.get("id")
            if sku and p_id:
                fixtures.products_by_sku[str(sku).strip()] = int(p_id)
    except Exception as exc:
        raise RuntimeError(f"Failed to query store products for fixture resolution: {exc}") from exc

    # 2. Resolve Orders
    try:
        order_res_raw = await mcp_client.call_tool("woo_list_orders", {"page": 1, "per_page": 100})
        order_data = json.loads(order_res_raw) if isinstance(order_res_raw, str) else order_res_raw
        order_items = order_data.get("items", []) if isinstance(order_data, dict) else []
        for item in order_items:
            o_id = item.get("id")
            if not o_id:
                continue
            o_id_int = int(o_id)

            # Map transaction ID
            tx_id = item.get("transaction_id")
            if tx_id:
                fixtures.orders_by_tx_id[str(tx_id).strip()] = o_id_int

            # Map seed_id from meta if present or fallback
            for meta in item.get("meta_data", []):
                if meta.get("key") == "_seed_id" and meta.get("value"):
                    fixtures.orders_by_seed_id[str(meta["value"]).strip()] = o_id_int

    except Exception as exc:
        raise RuntimeError(f"Failed to query store orders for fixture resolution: {exc}") from exc

    # Validate essential fixtures exist
    required_products = ["PROD-STARTER-PLAN", "PROD-MERCHANT-PRO", "PROD-PREMIUM-ANNUAL"]
    for sku in required_products:
        if sku not in fixtures.products_by_sku:
            raise RuntimeError(
                f"Required seeded product '{sku}' not found in store. "
                "Ensure local store has been populated with seed fixtures."
            )

    required_tx_ids = [
        "pay_fail_004_insufficient_funds",
        "pay_det_005_refunded",
        "pay_det_007_partial_refund",
        "pay_fail_011_otp_timeout",
        "pay_det_012_multi_item",
    ]
    for tx_id in required_tx_ids:
        if tx_id not in fixtures.orders_by_tx_id:
            raise RuntimeError(
                f"Required seeded order with transaction_id '{tx_id}' not found in store. "
                "Ensure local store has been populated with seed fixtures."
            )

    return fixtures
