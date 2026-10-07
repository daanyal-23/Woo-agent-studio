"""Unit and integration-mocked tests for WooCommerce store seeding."""

import pytest
import respx
from httpx import Response
from pydantic import SecretStr

from woo_connector.client import WooCommerceClient
from woo_connector.config import SeedConfig, WooCommerceConfig
from woo_connector.errors import WooCommerceConfigError
from woo_connector.seed import find_existing_product_skus, find_existing_seed_order_ids, seed_store
from woo_connector.seed_data import SEED_ORDERS, SEED_PRODUCTS


def test_deterministic_product_skus() -> None:
    assert len(SEED_PRODUCTS) == 5
    skus = [p["sku"] for p in SEED_PRODUCTS]
    assert len(set(skus)) == 5
    for sku in skus:
        assert sku.startswith("PROD-")


def test_deterministic_order_seed_ids() -> None:
    assert len(SEED_ORDERS) == 12
    seed_ids = [o["seed_id"] for o in SEED_ORDERS]
    assert len(set(seed_ids)) == 12
    for s_id in seed_ids:
        assert s_id.startswith("seed_order_")


def test_seed_config_requires_explicit_confirmation() -> None:
    config = SeedConfig(
        base_url="https://test.local/wp-json/wc/v3",
        seed_consumer_key="ck_seed_test",
        seed_consumer_secret=SecretStr("cs_seed_test"),
        seed_enabled=False,
    )
    with pytest.raises(WooCommerceConfigError, match="SEED_WOOCOMMERCE=1"):
        config.to_client_config()


def test_seed_config_requires_seed_credentials() -> None:
    config = SeedConfig(
        base_url="https://test.local/wp-json/wc/v3",
        seed_consumer_key="",
        seed_consumer_secret=SecretStr(""),
        seed_enabled=True,
    )
    with pytest.raises(WooCommerceConfigError, match="WOO_SEED_CONSUMER_KEY"):
        config.to_client_config()


def test_seed_config_enforces_https_unless_explicitly_permitted() -> None:
    config = SeedConfig(
        base_url="http://insecure.local/wp-json/wc/v3",
        seed_consumer_key="ck_seed",
        seed_consumer_secret=SecretStr("cs_seed"),
        seed_enabled=True,
        allow_insecure_http=False,
    )
    with pytest.raises(WooCommerceConfigError, match="Insecure HTTP is disabled"):
        config.to_client_config()


@respx.mock
def test_seed_creates_missing_products_and_orders(test_config: WooCommerceConfig) -> None:
    base = test_config.base_url.rstrip("/")

    # Initially store is empty
    respx.get(f"{base}/products").mock(
        return_value=Response(200, json=[], headers={"X-WP-Total": "0", "X-WP-TotalPages": "0"})
    )
    respx.get(f"{base}/orders").mock(
        return_value=Response(200, json=[], headers={"X-WP-Total": "0", "X-WP-TotalPages": "0"})
    )

    # Mock product creation
    post_product_route = respx.post(f"{base}/products").mock(
        side_effect=lambda req: Response(
            201,
            json={
                "id": 100,
                "name": "Mock Product",
                "sku": "PROD-MOCK",
                "price": "499.00",
                "status": "publish",
            },
        )
    )

    # Mock order creation
    post_order_route = respx.post(f"{base}/orders").mock(
        side_effect=lambda req: Response(
            201,
            json={
                "id": 500,
                "status": "completed",
                "currency": "INR",
                "total": "499.00",
                "meta_data": [{"key": "_seed_id", "value": "seed_order_mock"}],
            },
        )
    )

    with WooCommerceClient(config=test_config) as client:
        results = seed_store(client)

    assert results["products_created"] == 5
    assert results["products_existing"] == 0
    assert results["orders_created"] == 12
    assert results["orders_existing"] == 0
    assert len(results["failures"]) == 0

    assert post_product_route.call_count == 5
    assert post_order_route.call_count == 12


@respx.mock
def test_seed_skips_existing_products_and_orders(test_config: WooCommerceConfig) -> None:
    base = test_config.base_url.rstrip("/")

    # All products and orders already exist
    existing_products_data = [
        {"id": i, "name": p["name"], "sku": p["sku"], "price": "100.00", "status": "publish"}
        for i, p in enumerate(SEED_PRODUCTS, start=1)
    ]
    existing_orders_data = [
        {
            "id": i,
            "status": o["status"],
            "currency": "INR",
            "total": "500.00",
            "meta_data": [{"key": "_seed_id", "value": o["seed_id"]}],
        }
        for i, o in enumerate(SEED_ORDERS, start=1)
    ]

    respx.get(f"{base}/products").mock(
        return_value=Response(
            200, json=existing_products_data, headers={"X-WP-Total": "5", "X-WP-TotalPages": "1"}
        )
    )
    respx.get(f"{base}/orders").mock(
        return_value=Response(
            200, json=existing_orders_data, headers={"X-WP-Total": "12", "X-WP-TotalPages": "1"}
        )
    )

    post_product_route = respx.post(f"{base}/products").mock(
        return_value=Response(201, json={"id": 999})
    )
    post_order_route = respx.post(f"{base}/orders").mock(
        return_value=Response(201, json={"id": 999})
    )

    with WooCommerceClient(config=test_config) as client:
        results = seed_store(client)

    assert results["products_created"] == 0
    assert results["products_existing"] == 5
    assert results["orders_created"] == 0
    assert results["orders_existing"] == 12
    assert len(results["failures"]) == 0

    # No POSTs should have been made
    assert post_product_route.call_count == 0
    assert post_order_route.call_count == 0


@respx.mock
def test_order_idempotency_detects_orders_across_multiple_pages(
    test_config: WooCommerceConfig,
) -> None:
    base = test_config.base_url.rstrip("/")

    # Page 1 contains orders 1 to 6
    page_1_orders = [
        {
            "id": i,
            "status": o["status"],
            "currency": "INR",
            "total": "500.00",
            "meta_data": [{"key": "_seed_id", "value": o["seed_id"]}],
        }
        for i, o in enumerate(SEED_ORDERS[:6], start=1)
    ]

    # Page 2 contains orders 7 to 12
    page_2_orders = [
        {
            "id": i,
            "status": o["status"],
            "currency": "INR",
            "total": "500.00",
            "meta_data": [{"key": "_seed_id", "value": o["seed_id"]}],
        }
        for i, o in enumerate(SEED_ORDERS[6:], start=7)
    ]

    def orders_router(request):
        page = request.url.params.get("page", "1")
        if page == "1":
            return Response(
                200, json=page_1_orders, headers={"X-WP-Total": "12", "X-WP-TotalPages": "2"}
            )
        elif page == "2":
            return Response(
                200, json=page_2_orders, headers={"X-WP-Total": "12", "X-WP-TotalPages": "2"}
            )
        return Response(200, json=[], headers={"X-WP-Total": "12", "X-WP-TotalPages": "2"})

    respx.get(f"{base}/orders").mock(side_effect=orders_router)

    with WooCommerceClient(config=test_config) as client:
        found_ids = find_existing_seed_order_ids(client)

    assert len(found_ids) == 12
    expected_ids = {o["seed_id"] for o in SEED_ORDERS}
    assert found_ids == expected_ids


@respx.mock
def test_product_idempotency_across_multiple_pages(test_config: WooCommerceConfig) -> None:
    base = test_config.base_url.rstrip("/")

    page_1_prods = [
        {"id": 1, "sku": "PROD-STARTER-PLAN"},
        {"id": 2, "sku": "PROD-MERCHANT-PRO"},
    ]
    page_2_prods = [
        {"id": 3, "sku": "PROD-PREMIUM-ANNUAL"},
        {"id": 4, "sku": "PROD-GATEWAY-ADDON"},
        {"id": 5, "sku": "PROD-ENTERPRISE-SUPPORT"},
    ]

    def products_router(request):
        page = request.url.params.get("page", "1")
        if page == "1":
            return Response(
                200, json=page_1_prods, headers={"X-WP-Total": "5", "X-WP-TotalPages": "2"}
            )
        elif page == "2":
            return Response(
                200, json=page_2_prods, headers={"X-WP-Total": "5", "X-WP-TotalPages": "2"}
            )
        return Response(200, json=[], headers={"X-WP-Total": "5", "X-WP-TotalPages": "2"})

    respx.get(f"{base}/products").mock(side_effect=products_router)

    with WooCommerceClient(config=test_config) as client:
        found_skus = find_existing_product_skus(client)

    assert len(found_skus) == 5
    expected_skus = {p["sku"] for p in SEED_PRODUCTS}
    assert found_skus == expected_skus


@respx.mock
def test_seed_never_issues_delete_requests(test_config: WooCommerceConfig) -> None:
    base = test_config.base_url.rstrip("/")

    # Seed partial: 2 products and 2 orders exist
    respx.get(f"{base}/products").mock(
        return_value=Response(
            200,
            json=[{"id": 1, "sku": "PROD-STARTER-PLAN", "price": "10.00"}],
            headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"},
        )
    )
    respx.get(f"{base}/orders").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": 10,
                    "meta_data": [{"key": "_seed_id", "value": "seed_order_001"}],
                    "total": "10.00",
                }
            ],
            headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"},
        )
    )
    respx.post(f"{base}/products").mock(
        return_value=Response(201, json={"id": 200, "sku": "PROD-NEW", "price": "10.00"})
    )
    respx.post(f"{base}/orders").mock(
        return_value=Response(
            201,
            json={
                "id": 300,
                "meta_data": [{"key": "_seed_id", "value": "seed_order_new"}],
                "total": "10.00",
            },
        )
    )

    delete_route = respx.route(method="DELETE").mock(
        return_value=Response(200, json={"deleted": True})
    )

    with WooCommerceClient(config=test_config) as client:
        seed_store(client)

    # Strictly 0 DELETE operations performed
    assert delete_route.call_count == 0


@respx.mock
def test_seed_error_handling_captures_failures_cleanly(
    test_config: WooCommerceConfig,
    deterministic_retry_policy,
) -> None:
    base = test_config.base_url.rstrip("/")

    respx.get(f"{base}/products").mock(
        return_value=Response(200, json=[], headers={"X-WP-Total": "0", "X-WP-TotalPages": "0"})
    )
    respx.get(f"{base}/orders").mock(
        return_value=Response(200, json=[], headers={"X-WP-Total": "0", "X-WP-TotalPages": "0"})
    )

    # Simulate 400 Bad Request on creating products
    respx.post(f"{base}/products").mock(
        return_value=Response(
            400,
            json={
                "code": "woocommerce_rest_cannot_create",
                "message": "Sorry, you are not allowed to create resources.",
            },
        )
    )
    # Simulate 500 error on creating orders
    respx.post(f"{base}/orders").mock(
        return_value=Response(
            500,
            json={
                "code": "internal_server_error",
                "message": "Database write failure.",
            },
        )
    )

    with WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy) as client:
        results = seed_store(client)

    assert results["products_created"] == 0
    assert results["orders_created"] == 0
    assert len(results["failures"]) == 17  # 5 products + 12 orders failed cleanly
    assert all(
        "woocommerce_rest_cannot_create" in f or "Database write failure" in f
        for f in results["failures"]
    )


def test_seed_credentials_never_exposed_in_string_or_repr() -> None:
    secret_value = "super_secret_write_key_xyz_987"
    config = SeedConfig(
        base_url="https://store.example.com/wp-json/wc/v3",
        seed_consumer_key="ck_write_key_123",
        seed_consumer_secret=SecretStr(secret_value),
        seed_enabled=True,
    )

    # Verify secret string masking
    assert secret_value not in repr(config)
    assert secret_value not in str(config)
    assert secret_value not in str(config.seed_consumer_secret)
