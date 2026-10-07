"""Idempotent seed script to populate local WooCommerce store with fictional test data."""

import sys
from typing import Any

from woo_connector.client import WooCommerceClient
from woo_connector.config import SeedConfig
from woo_connector.errors import WooCommerceConfigError, WooCommerceError
from woo_connector.models.order import Order
from woo_connector.models.product import Product
from woo_connector.seed_data import SEED_ORDERS, SEED_PRODUCTS


def find_existing_product_skus(client: WooCommerceClient) -> set[str]:
    """Retrieve all existing product SKUs across all pages in WooCommerce."""
    existing_skus: set[str] = set()
    all_target_skus = {prod["sku"] for prod in SEED_PRODUCTS}
    page = 1

    while True:
        resp = client.get("products", params={"page": page, "per_page": 100})
        items = resp.data
        if not isinstance(items, list) or len(items) == 0:
            break

        for item in items:
            if isinstance(item, dict):
                sku = str(item.get("sku") or "").strip()
                if sku:
                    existing_skus.add(sku)

        if all_target_skus.issubset(existing_skus):
            break

        total_pages = resp.total_pages
        if total_pages is not None and page >= total_pages:
            break
        page += 1

    return existing_skus


def find_existing_seed_order_ids(client: WooCommerceClient) -> set[str]:
    """Retrieve all existing deterministic _seed_id values across all pages of orders."""
    existing_seed_ids: set[str] = set()
    all_target_seed_ids = {order["seed_id"] for order in SEED_ORDERS}
    page = 1

    while True:
        resp = client.get("orders", params={"page": page, "per_page": 100})
        items = resp.data
        if not isinstance(items, list) or len(items) == 0:
            break

        for item in items:
            if isinstance(item, dict):
                for meta in item.get("meta_data") or []:
                    if isinstance(meta, dict) and meta.get("key") == "_seed_id":
                        val = meta.get("value")
                        if val:
                            existing_seed_ids.add(str(val).strip())

        if all_target_seed_ids.issubset(existing_seed_ids):
            break

        total_pages = resp.total_pages
        if total_pages is not None and page >= total_pages:
            break
        page += 1

    return existing_seed_ids


def seed_store(client: WooCommerceClient) -> dict[str, Any]:
    """Run idempotent seeding of fictional products and orders.

    Guarantees:
    - Never deletes or modifies unrelated data.
    - Idempotent: Skips already-seeded products (matched by SKU) and orders (matched by _seed_id).
    - Uses only POST /products and POST /orders for new items.
    """
    results: dict[str, Any] = {
        "products_created": 0,
        "products_existing": 0,
        "orders_created": 0,
        "orders_existing": 0,
        "failures": [],
    }

    # 1. Product Idempotency Check & Creation
    existing_skus = find_existing_product_skus(client)
    for prod_data in SEED_PRODUCTS:
        sku = prod_data["sku"]
        if sku in existing_skus:
            results["products_existing"] += 1
            continue

        try:
            resp = client.post("products", json=prod_data)
            # Verify response schema without logging raw payloads
            Product.from_woocommerce(resp.data)
            results["products_created"] += 1
            existing_skus.add(sku)
        except WooCommerceError as err:
            results["failures"].append(f"Product '{sku}' [{err.code}]: {err.message}")
        except Exception as exc:
            results["failures"].append(f"Product '{sku}': {type(exc).__name__}")

    # 2. Order Idempotency Check & Creation
    existing_seed_ids = find_existing_seed_order_ids(client)
    for order_data in SEED_ORDERS:
        seed_id = order_data["seed_id"]
        if seed_id in existing_seed_ids:
            results["orders_existing"] += 1
            continue

        payload = {
            "status": order_data["status"],
            "currency": order_data["currency"],
            "payment_method": order_data["payment_method"],
            "payment_method_title": order_data["payment_method_title"],
            "transaction_id": order_data["transaction_id"],
            "billing": order_data["billing"],
            "line_items": order_data["line_items"],
            "meta_data": order_data["meta_data"],
        }
        try:
            resp = client.post("orders", json=payload)
            # Verify and normalize response without logging raw customer PII
            Order.from_woocommerce(resp.data)
            results["orders_created"] += 1
            existing_seed_ids.add(seed_id)
        except WooCommerceError as err:
            results["failures"].append(f"Order '{seed_id}' [{err.code}]: {err.message}")
        except Exception as exc:
            results["failures"].append(f"Order '{seed_id}': {type(exc).__name__}")

    return results


def main() -> int:
    """CLI entrypoint for running WooCommerce store seeding."""
    print("WARNING: This will create fictional seed data in the configured WooCommerce store.")

    try:
        seed_config = SeedConfig()
        client_config = seed_config.to_client_config()
    except WooCommerceConfigError as err:
        print(f"Configuration Refusal: {err}", file=sys.stderr)
        return 1

    print("Preconditions satisfied. Connecting to WooCommerce store...")

    try:
        with WooCommerceClient(config=client_config) as client:
            results = seed_store(client)

        print("\n--- Seeding Summary ---")
        print(f"Products Created : {results['products_created']}")
        print(f"Products Existing: {results['products_existing']}")
        print(f"Orders Created   : {results['orders_created']}")
        print(f"Orders Existing  : {results['orders_existing']}")

        if results["failures"]:
            print(f"Failures ({len(results['failures'])}):", file=sys.stderr)
            for fail in results["failures"]:
                print(f"  - {fail}", file=sys.stderr)
            return 1

        print("Seeding completed successfully.")
        return 0

    except Exception as exc:
        print(f"Unexpected Seeding Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
