"""Optional live integration smoke test.

Skipped unless explicitly enabled via WOO_LIVE_TEST=1 and required credentials are set.
Performs a read-only GET /wp-json/wc/v3/orders?per_page=1.
Does NOT create, update, or delete any resources.
"""

import os

import pytest

from woo_connector.client import WooCommerceClient
from woo_connector.config import WooCommerceConfig

LIVE_TEST_ENABLED = os.getenv("WOO_LIVE_TEST") == "1"
BASE_URL = os.getenv("WOO_BASE_URL")
CONSUMER_KEY = os.getenv("WOO_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("WOO_CONSUMER_SECRET")
ALLOW_INSECURE = os.getenv("WOO_ALLOW_INSECURE_HTTP", "false").lower() in ("true", "1")

skip_condition = not (LIVE_TEST_ENABLED and BASE_URL and CONSUMER_KEY and CONSUMER_SECRET)
skip_reason = (
    "Live integration smoke test disabled. Set WOO_LIVE_TEST=1 and WooCommerce credentials."
)


@pytest.mark.live
@pytest.mark.skipif(skip_condition, reason=skip_reason)
def test_live_smoke_orders_per_page_one() -> None:
    """Read-only live smoke test querying GET /wp-json/wc/v3/orders?per_page=1."""
    config = WooCommerceConfig(
        base_url=BASE_URL,
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        allow_insecure_http=ALLOW_INSECURE,
        timeout_seconds=15.0,
    )

    with WooCommerceClient(config=config) as client:
        response = client.get("orders", params={"per_page": 1})

    assert response.status_code == 200
    assert isinstance(response.data, list)
    # Validate optional pagination headers if populated by WooCommerce
    if response.total_count is not None:
        assert isinstance(response.total_count, int)
    if response.total_pages is not None:
        assert isinstance(response.total_pages, int)
