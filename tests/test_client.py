"""Deterministic client unit tests covering all required cases using respx."""

import base64

import httpx
import pytest
import respx

from tests.conftest import SleepSpy
from woo_connector.client import WooCommerceClient
from woo_connector.config import WooCommerceConfig
from woo_connector.errors import (
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    ResponseParseError,
    ServerError,
)
from woo_connector.retry import RetryPolicy


@respx.mock
def test_successful_get_with_parsed_headers(test_config: WooCommerceConfig) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    mock_headers = {
        "Content-Type": "application/json",
        "X-WP-Total": "42",
        "X-WP-TotalPages": "5",
    }
    route = respx.get(url).respond(
        status_code=200,
        headers=mock_headers,
        json=[{"id": 101, "status": "completed"}],
    )

    with WooCommerceClient(config=test_config) as client:
        response = client.get("orders")

    assert route.called
    assert response.status_code == 200
    assert response.data == [{"id": 101, "status": "completed"}]
    assert response.total_count == 42
    assert response.total_pages == 5


@respx.mock
def test_basic_authentication_correctly_attached(test_config: WooCommerceConfig) -> None:
    url = "https://test-store.local/wp-json/wc/v3/system_status"
    route = respx.get(url).respond(status_code=200, json={"status": "ok"})

    with WooCommerceClient(config=test_config) as client:
        client.get("system_status")

    assert route.called
    sent_request = route.calls.last.request
    assert "Authorization" in sent_request.headers

    auth_header = sent_request.headers["Authorization"]
    assert auth_header.startswith("Basic ")
    token = auth_header.split(" ", 1)[1]
    decoded = base64.b64decode(token).decode("utf-8")
    expected = f"{test_config.consumer_key}:{test_config.secret_value}"
    assert decoded == expected


def test_base_url_normalization_preserves_path(test_config: WooCommerceConfig) -> None:
    with WooCommerceClient(config=test_config) as client:
        assert client._build_url("orders") == "https://test-store.local/wp-json/wc/v3/orders"
        assert client._build_url("/orders") == "https://test-store.local/wp-json/wc/v3/orders"
        assert client._build_url("") == "https://test-store.local/wp-json/wc/v3"


def test_timeout_configuration_applied(test_config: WooCommerceConfig) -> None:
    with WooCommerceClient(config=test_config) as client:
        assert client._client.timeout.read == test_config.timeout_seconds


@respx.mock
def test_error_400_bad_request_no_retry(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/products"
    route = respx.get(url).respond(
        status_code=400,
        json={"code": "rest_invalid_param", "message": "Invalid parameter: page"},
    )

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    with pytest.raises(BadRequestError) as exc_info:
        client.get("products")

    assert route.call_count == 1
    assert len(sleep_spy.calls) == 0
    assert exc_info.value.code == "rest_invalid_param"
    assert exc_info.value.status_code == 400
    assert exc_info.value.retryable is False


@respx.mock
def test_error_401_authentication_no_retry(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    route = respx.get(url).respond(
        status_code=401,
        json={"code": "woocommerce_rest_cannot_view", "message": "Invalid credentials"},
    )

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    with pytest.raises(AuthenticationError) as exc_info:
        client.get("orders")

    assert route.call_count == 1
    assert len(sleep_spy.calls) == 0
    assert exc_info.value.status_code == 401
    assert exc_info.value.retryable is False


@respx.mock
def test_error_403_forbidden_no_retry(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/settings"
    route = respx.get(url).respond(
        status_code=403,
        json={"code": "woocommerce_rest_cannot_view", "message": "Access forbidden"},
    )

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    with pytest.raises(PermissionDeniedError):
        client.get("settings")

    assert route.call_count == 1
    assert len(sleep_spy.calls) == 0


@respx.mock
def test_error_404_not_found_no_retry(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/unknown"
    route = respx.get(url).respond(
        status_code=404,
        json={"code": "rest_no_route", "message": "No route was found"},
    )

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    with pytest.raises(NotFoundError):
        client.get("unknown")

    assert route.call_count == 1
    assert len(sleep_spy.calls) == 0


@respx.mock
def test_error_429_retries_and_succeeds(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(
            status_code=429,
            headers={"Retry-After": "2"},
            json={"code": "rate_limit_exceeded", "message": "Too many requests"},
        ),
        httpx.Response(status_code=200, json=[{"id": 1}]),
    ]

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    response = client.get("orders")

    assert route.call_count == 2
    assert sleep_spy.calls == [2.0]
    assert response.status_code == 200
    assert response.data == [{"id": 1}]


@respx.mock
def test_error_500_retries_and_succeeds(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(
            status_code=500, json={"code": "internal_error", "message": "Database error"}
        ),
        httpx.Response(status_code=200, json=[]),
    ]

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    response = client.get("orders")

    assert route.call_count == 2
    assert len(sleep_spy.calls) == 1
    assert sleep_spy.calls[0] == 0.5  # backoff_factor * 2^0
    assert response.status_code == 200


@respx.mock
def test_error_502_503_server_errors_retry(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(status_code=502, text="Bad Gateway"),
        httpx.Response(status_code=503, text="Service Unavailable"),
        httpx.Response(status_code=200, json={"ok": True}),
    ]

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    response = client.get("orders")

    assert route.call_count == 3
    assert len(sleep_spy.calls) == 2
    assert sleep_spy.calls == [0.5, 1.0]
    assert response.status_code == 200


@respx.mock
def test_network_timeout_retries_and_succeeds(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    route = respx.get(url)
    route.side_effect = [
        httpx.ConnectTimeout("Connection timed out"),
        httpx.Response(status_code=200, json=[]),
    ]

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    response = client.get("orders")

    assert route.call_count == 2
    assert len(sleep_spy.calls) == 1
    assert response.status_code == 200


@respx.mock
def test_retry_after_cap_enforced_in_client(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(status_code=429, headers={"Retry-After": "100"}, json={}),
        httpx.Response(status_code=200, json=[]),
    ]

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    client.get("orders")

    assert route.call_count == 2
    # Capped at 30.0 instead of 100.0
    assert sleep_spy.calls == [30.0]


@respx.mock
def test_max_retries_exhausted_raises_final_error(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
    deterministic_retry_policy: RetryPolicy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    route = respx.get(url).respond(status_code=500, text="Internal Server Error")

    client = WooCommerceClient(config=test_config, retry_policy=deterministic_retry_policy)
    with pytest.raises(ServerError) as exc_info:
        client.get("orders")

    # Initial attempt + 3 retries = 4 total attempts
    assert route.call_count == 4
    assert len(sleep_spy.calls) == 3
    assert exc_info.value.status_code == 500


@respx.mock
def test_total_retry_time_budget_prevents_excessive_sleep(
    test_config: WooCommerceConfig,
    sleep_spy: SleepSpy,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    # Small budget: 5 seconds
    budget_policy = RetryPolicy(
        max_retries=5,
        backoff_factor=1.0,
        jitter=False,
        max_retry_after=30.0,
        total_timeout_budget=5.0,
        sleep_fn=sleep_spy,
    )
    # Delays: 1.0, 2.0, 4.0 -> sum reaches 7 > 5 budget
    route = respx.get(url).respond(status_code=500, text="Down")

    client = WooCommerceClient(config=test_config, retry_policy=budget_policy)
    with pytest.raises(ServerError):
        client.get("orders")

    # First attempt: sleep 1.0 (total=1.0 <= 5)
    # Second attempt: sleep 2.0 (total=3.0 <= 5)
    # Third attempt: would sleep 4.0 (total=7.0 > 5 budget) -> stops!
    assert sleep_spy.calls == [1.0, 2.0]
    assert route.call_count == 3


@respx.mock
def test_200_html_response_raises_response_parse_error(
    test_config: WooCommerceConfig,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    html_content = "<html><body><h1>Maintenance Mode</h1></body></html>"
    respx.get(url).respond(
        status_code=200,
        headers={"Content-Type": "text/html"},
        text=html_content,
    )

    with WooCommerceClient(config=test_config) as client:
        with pytest.raises(ResponseParseError) as exc_info:
            client.get("orders")

    assert exc_info.value.code == "response_parse_error"
    assert exc_info.value.status_code == 200
    assert exc_info.value.retryable is False
    assert "Maintenance Mode" in exc_info.value.message


@respx.mock
def test_malformed_json_response_raises_response_parse_error(
    test_config: WooCommerceConfig,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    respx.get(url).respond(
        status_code=200,
        headers={"Content-Type": "application/json"},
        text="[{id: 123 broken_json",
    )

    with WooCommerceClient(config=test_config) as client:
        with pytest.raises(ResponseParseError) as exc_info:
            client.get("orders")

    assert exc_info.value.code == "response_parse_error"
    assert exc_info.value.status_code == 200


@respx.mock
def test_headers_total_and_total_pages_none_when_missing(
    test_config: WooCommerceConfig,
) -> None:
    url = "https://test-store.local/wp-json/wc/v3/orders"
    respx.get(url).respond(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=[],
    )

    with WooCommerceClient(config=test_config) as client:
        response = client.get("orders")

    assert response.total_count is None
    assert response.total_pages is None
