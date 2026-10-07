"""Unit tests for OrderService using RESPX HTTP-level mocking."""

import pytest
import respx
from httpx import Response

from woo_connector.client import WooCommerceClient
from woo_connector.config import WooCommerceConfig
from woo_connector.errors import (
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)
from woo_connector.orders import OrderService


@pytest.fixture
def order_client(test_config: WooCommerceConfig) -> WooCommerceClient:
    return WooCommerceClient(config=test_config)


@pytest.fixture
def order_service(order_client: WooCommerceClient) -> OrderService:
    return OrderService(client=order_client)


SAMPLE_RAW_ORDER = {
    "id": 5001,
    "status": "completed",
    "currency": "INR",
    "total": "1499.00",
    "total_tax": "0.00",
    "payment_method": "razorpay",
    "payment_method_title": "Razorpay Secure Gateway",
    "transaction_id": "pay_test_001",
    "date_created": "2026-10-05T14:30:00Z",
    "date_paid": "2026-10-05T14:31:00Z",
    "billing": {
        "first_name": "Dev",
        "last_name": "Merchant",
        "email": "dev.merchant@example.com",
        "phone": "+91 9999999999",
        "address_1": "123 Commercial St",
        "city": "Mumbai",
        "postcode": "400001",
    },
    "customer_note": "Internal secret notes from customer",
    "line_items": [
        {
            "id": 10,
            "product_id": 14,
            "name": "Merchant Pro Plan",
            "sku": "PROD-MERCHANT-PRO",
            "quantity": 1,
            "subtotal": "1499.00",
            "total": "1499.00",
        }
    ],
    "meta_data": [
        {"key": "_seed_id", "value": "order_seed_001"},
        {"key": "_secret_merchant_data", "value": "secret"},
    ],
    "refunds": [],
}


@respx.mock
def test_list_orders_success_and_pagination(order_service: OrderService) -> None:
    respx.get("https://test-store.local/wp-json/wc/v3/orders").mock(
        return_value=Response(
            200,
            json=[SAMPLE_RAW_ORDER],
            headers={"X-WP-Total": "12", "X-WP-TotalPages": "3"},
        )
    )

    result = order_service.list_orders(page=1, per_page=4)

    assert len(result.items) == 1
    assert result.page == 1
    assert result.per_page == 4
    assert result.total_count == 12
    assert result.total_pages == 3
    assert result.has_more is True
    assert result.next_page == 2

    # Check order normalization & PII minimization
    order = result.items[0]
    assert order.id == 5001
    assert order.status == "completed"
    assert order.customer_name == "Dev Merchant"
    assert order.customer_email_masked == "d***t@example.com"
    assert not hasattr(order, "phone")
    assert not hasattr(order, "customer_note")
    assert not hasattr(order, "address_1")
    assert len(order.line_items) == 1
    assert order.line_items[0].sku == "PROD-MERCHANT-PRO"


@respx.mock
def test_list_orders_final_page(order_service: OrderService) -> None:
    respx.get("https://test-store.local/wp-json/wc/v3/orders").mock(
        return_value=Response(
            200,
            json=[SAMPLE_RAW_ORDER],
            headers={"X-WP-Total": "12", "X-WP-TotalPages": "3"},
        )
    )

    result = order_service.list_orders(page=3, per_page=4)

    assert result.page == 3
    assert result.total_pages == 3
    assert result.has_more is False
    assert result.next_page is None


@respx.mock
def test_list_orders_missing_headers_adjustment_one(order_service: OrderService) -> None:
    """Adjustment 1: If headers are missing, has_more=False, next_page=None."""
    respx.get("https://test-store.local/wp-json/wc/v3/orders").mock(
        return_value=Response(200, json=[SAMPLE_RAW_ORDER], headers={})
    )

    result = order_service.list_orders(page=1, per_page=10)

    assert result.total_count is None
    assert result.total_pages is None
    assert result.has_more is False
    assert result.next_page is None


@respx.mock
def test_list_orders_status_filtering(order_service: OrderService) -> None:
    route = respx.get("https://test-store.local/wp-json/wc/v3/orders").mock(
        return_value=Response(200, json=[SAMPLE_RAW_ORDER])
    )

    order_service.list_orders(page=1, per_page=10, status="completed")

    assert route.called
    params = route.calls.last.request.url.params
    assert params["status"] == "completed"


@respx.mock
def test_get_order_success(order_service: OrderService) -> None:
    respx.get("https://test-store.local/wp-json/wc/v3/orders/5001").mock(
        return_value=Response(200, json=SAMPLE_RAW_ORDER)
    )

    order = order_service.get_order(5001)

    assert order.id == 5001
    assert order.total == "1499.00"
    assert order.customer_email_masked == "d***t@example.com"
    assert order.seed_id == "order_seed_001"


@respx.mock
def test_get_order_404_not_found(order_service: OrderService) -> None:
    respx.get("https://test-store.local/wp-json/wc/v3/orders/9999").mock(
        return_value=Response(
            404,
            json={"code": "woocommerce_rest_shop_order_invalid_id", "message": "Invalid ID."},
        )
    )

    with pytest.raises(NotFoundError) as exc_info:
        order_service.get_order(9999)

    assert exc_info.value.status_code == 404


@respx.mock
def test_search_orders_success(order_service: OrderService) -> None:
    route = respx.get("https://test-store.local/wp-json/wc/v3/orders").mock(
        return_value=Response(
            200,
            json=[SAMPLE_RAW_ORDER],
            headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"},
        )
    )

    result = order_service.search_orders("Dev", page=1, per_page=5, status="completed")

    assert route.called
    params = route.calls.last.request.url.params
    assert params["search"] == "Dev"
    assert params["status"] == "completed"
    assert params["page"] == "1"
    assert params["per_page"] == "5"

    assert len(result.items) == 1
    assert result.items[0].id == 5001


def test_order_input_validation(order_service: OrderService) -> None:
    with pytest.raises(ValueError, match="page must be an integer >= 1"):
        order_service.list_orders(page=0)

    with pytest.raises(ValueError, match="per_page must be an integer between 1 and 100"):
        order_service.list_orders(per_page=101)

    with pytest.raises(ValueError, match="order_id must be a positive integer"):
        order_service.get_order(0)

    with pytest.raises(ValueError, match="search query must be a non-empty string"):
        order_service.search_orders("   ")


@respx.mock
def test_order_service_propagates_client_errors(order_service: OrderService) -> None:
    respx.get("https://test-store.local/wp-json/wc/v3/orders").mock(
        return_value=Response(400, json={"code": "bad_request", "message": "Bad status filter."})
    )

    with pytest.raises(BadRequestError):
        order_service.list_orders(status="invalid")

    respx.get("https://test-store.local/wp-json/wc/v3/orders/1").mock(
        return_value=Response(403, json={"code": "forbidden", "message": "No permission."})
    )

    with pytest.raises(PermissionDeniedError):
        order_service.get_order(1)
