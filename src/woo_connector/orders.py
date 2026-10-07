from typing import Any, Literal

from woo_connector.client import WooCommerceClient
from woo_connector.errors import InvalidInputError, ResponseParseError
from woo_connector.models.order import Order
from woo_connector.models.pagination import PaginatedResult

MIN_PER_PAGE: int = 1
MAX_PER_PAGE: int = 100
DEFAULT_PAGE: int = 1
DEFAULT_PER_PAGE: int = 10

OrderStatus = Literal[
    "pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"
]


class OrderService:
    """Read-only order operations querying the official WooCommerce REST API."""

    def __init__(self, client: WooCommerceClient) -> None:
        self._client = client

    @staticmethod
    def _validate_pagination_params(page: int, per_page: int) -> None:
        if not isinstance(page, int) or page < MIN_PER_PAGE:
            raise InvalidInputError(f"page must be an integer >= {MIN_PER_PAGE}, got {page!r}")
        if not isinstance(per_page, int) or per_page < MIN_PER_PAGE or per_page > MAX_PER_PAGE:
            msg = (
                f"per_page must be an integer between {MIN_PER_PAGE} and {MAX_PER_PAGE}, "
                f"got {per_page!r}"
            )
            raise InvalidInputError(msg)

    @staticmethod
    def _validate_order_id(order_id: int) -> None:
        if not isinstance(order_id, int) or order_id <= 0:
            raise InvalidInputError(f"order_id must be a positive integer, got {order_id!r}")

    def list_orders(
        self,
        page: int = 1,
        per_page: int = 10,
        status: str | None = None,
    ) -> PaginatedResult[Order]:
        """Fetch a paginated list of normalized, PII-minimized orders.

        Issues GET /orders with page, per_page, and optional status.
        """
        self._validate_pagination_params(page, per_page)

        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        if status is not None:
            cleaned_status = status.strip()
            if cleaned_status:
                params["status"] = cleaned_status

        response = self._client.get("orders", params=params)

        if not isinstance(response.data, list):
            raise ResponseParseError(
                f"Expected list response for orders list, got {type(response.data).__name__}"
            )

        items = [Order.from_woocommerce(o) for o in response.data if isinstance(o, dict)]
        return PaginatedResult.create(
            items=items,
            page=page,
            per_page=per_page,
            total_count=response.total_count,
            total_pages=response.total_pages,
        )

    def get_order(self, order_id: int) -> Order:
        """Fetch a single normalized, PII-minimized order by its integer ID.

        Issues GET /orders/{order_id}. Raises NotFoundError if not found.
        """
        self._validate_order_id(order_id)

        response = self._client.get(f"orders/{order_id}")

        if not isinstance(response.data, dict):
            msg = f"Expected dict response for order {order_id}, got {type(response.data).__name__}"
            raise ResponseParseError(msg)

        return Order.from_woocommerce(response.data)

    def search_orders(
        self,
        query: str,
        page: int = 1,
        per_page: int = 10,
        status: str | None = None,
    ) -> PaginatedResult[Order]:
        """Search orders using WooCommerce native `search` parameter.

        Issues GET /orders?search=<query>.
        Does not imply server-side matching on arbitrary customer or transaction fields.
        """
        if not isinstance(query, str) or not query.strip():
            raise InvalidInputError("search query must be a non-empty string")

        self._validate_pagination_params(page, per_page)

        params: dict[str, Any] = {
            "search": query.strip(),
            "page": page,
            "per_page": per_page,
        }
        if status is not None:
            cleaned_status = status.strip()
            if cleaned_status:
                params["status"] = cleaned_status

        response = self._client.get("orders", params=params)

        if not isinstance(response.data, list):
            raise ResponseParseError(
                f"Expected list response for order search, got {type(response.data).__name__}"
            )

        items = [Order.from_woocommerce(o) for o in response.data if isinstance(o, dict)]
        return PaginatedResult.create(
            items=items,
            page=page,
            per_page=per_page,
            total_count=response.total_count,
            total_pages=response.total_pages,
        )
