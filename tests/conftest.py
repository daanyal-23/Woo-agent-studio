"""Shared test fixtures and deterministic mocks."""

import pytest

from woo_connector.config import WooCommerceConfig
from woo_connector.retry import RetryPolicy


class SleepSpy:
    """Records sleep durations without real-time delay."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def sleep_spy() -> SleepSpy:
    return SleepSpy()


@pytest.fixture
def test_config() -> WooCommerceConfig:
    return WooCommerceConfig(
        base_url="https://test-store.local/wp-json/wc/v3",
        consumer_key="ck_test_1234567890",
        consumer_secret="cs_test_secret_value_xyz",
        allow_insecure_http=False,
        timeout_seconds=10.0,
    )


@pytest.fixture
def insecure_test_config() -> WooCommerceConfig:
    return WooCommerceConfig(
        base_url="http://localhost:8080/wp-json/wc/v3",
        consumer_key="ck_local_dev_key",
        consumer_secret="cs_local_dev_secret",
        allow_insecure_http=True,
        timeout_seconds=10.0,
    )


@pytest.fixture
def deterministic_retry_policy(sleep_spy: SleepSpy) -> RetryPolicy:
    return RetryPolicy(
        max_retries=3,
        backoff_factor=0.5,
        jitter=False,
        max_retry_after=30.0,
        total_timeout_budget=60.0,
        sleep_fn=sleep_spy,
    )
