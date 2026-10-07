"""Opt-in live integration smoke verification for Phase B2 read-only services.

Skipped by default. Run only when WOO_LIVE_TEST=1 and live credentials are set:
    WOO_LIVE_TEST=1 python -m pytest -k test_live_phase_b2
"""

import os

import pytest

from woo_connector.client import WooCommerceClient
from woo_connector.config import WooCommerceConfig
from woo_connector.orders import OrderService
from woo_connector.products import ProductService

LIVE_TEST_ENABLED = os.getenv("WOO_LIVE_TEST") == "1"
BASE_URL = os.getenv("WOO_BASE_URL")
CONSUMER_KEY = os.getenv("WOO_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("WOO_CONSUMER_SECRET")
ALLOW_INSECURE = os.getenv("WOO_ALLOW_INSECURE_HTTP", "false").lower() in ("true", "1")

skip_condition = not (LIVE_TEST_ENABLED and BASE_URL and CONSUMER_KEY and CONSUMER_SECRET)
skip_reason = (
    "Live integration smoke test disabled. Set WOO_LIVE_TEST=1 and WooCommerce credentials."
)


@pytest.fixture
def live_client() -> WooCommerceClient:
    config = WooCommerceConfig(
        base_url=BASE_URL,
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        allow_insecure_http=ALLOW_INSECURE,
        timeout_seconds=15.0,
    )
    return WooCommerceClient(config=config)


@pytest.mark.live
@pytest.mark.skipif(skip_condition, reason=skip_reason)
def test_live_phase_b2_products_smoke(live_client: WooCommerceClient) -> None:
    product_service = ProductService(client=live_client)

    # 1. list_products(per_page=5)
    products_page = product_service.list_products(per_page=5)
    assert len(products_page.items) > 0
    assert products_page.page == 1

    # 2. search_products("Merchant")
    search_res = product_service.search_products("Merchant")
    assert len(search_res.items) >= 1
    assert any("Merchant" in p.name for p in search_res.items)

    # 3. get_product_by_sku("PROD-MERCHANT-PRO")
    sku_product = product_service.get_product_by_sku("PROD-MERCHANT-PRO")
    assert sku_product is not None
    assert sku_product.sku == "PROD-MERCHANT-PRO"

    # 4. get_product(sku_product.id)
    retrieved = product_service.get_product(sku_product.id)
    assert retrieved.id == sku_product.id
    assert retrieved.sku == "PROD-MERCHANT-PRO"


@pytest.mark.live
@pytest.mark.skipif(skip_condition, reason=skip_reason)
def test_live_phase_b2_orders_smoke(live_client: WooCommerceClient) -> None:
    order_service = OrderService(client=live_client)

    # 5. list_orders(per_page=5) with pagination check (12 total seeded)
    orders_p1 = order_service.list_orders(page=1, per_page=5)
    assert len(orders_p1.items) == 5
    assert orders_p1.total_count == 12
    assert orders_p1.has_more is True
    assert orders_p1.next_page == 2

    # 6. get_order(order_id)
    first_order_id = orders_p1.items[0].id
    order = order_service.get_order(first_order_id)
    assert order.id == first_order_id
    assert order.customer_email_masked is not None

    # 7. status filtering
    completed_orders = order_service.list_orders(status="completed", per_page=5)
    assert all(o.status == "completed" for o in completed_orders.items)

    # 8. search_orders
    searched = order_service.search_orders("Merchant", page=1, per_page=5)
    assert isinstance(searched.items, list)
