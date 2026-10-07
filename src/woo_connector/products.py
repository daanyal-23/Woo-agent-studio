from typing import Any, Literal

from woo_connector.client import WooCommerceClient
from woo_connector.errors import InvalidInputError, ResponseParseError
from woo_connector.models.pagination import PaginatedResult
from woo_connector.models.product import Product

MIN_PER_PAGE: int = 1
MAX_PER_PAGE: int = 100
DEFAULT_PAGE: int = 1
DEFAULT_PER_PAGE: int = 10

ProductStatus = Literal["publish", "draft", "pending", "private"]


class ProductService:
    """Read-only product operations querying the official WooCommerce REST API."""

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
    def _validate_product_id(product_id: int) -> None:
        if not isinstance(product_id, int) or product_id <= 0:
            raise InvalidInputError(f"product_id must be a positive integer, got {product_id!r}")

    def list_products(
        self,
        page: int = 1,
        per_page: int = 10,
        status: str | None = None,
    ) -> PaginatedResult[Product]:
        """Fetch a paginated list of products.

        Issues GET /products with page, per_page, and optional status.
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

        response = self._client.get("products", params=params)

        if not isinstance(response.data, list):
            raise ResponseParseError(
                f"Expected list response for products list, got {type(response.data).__name__}"
            )

        items = [Product.from_woocommerce(p) for p in response.data if isinstance(p, dict)]
        return PaginatedResult.create(
            items=items,
            page=page,
            per_page=per_page,
            total_count=response.total_count,
            total_pages=response.total_pages,
        )

    def get_product(self, product_id: int) -> Product:
        """Fetch a single normalized product by its integer ID.

        Issues GET /products/{product_id}. Raises NotFoundError if not found.
        """
        self._validate_product_id(product_id)

        response = self._client.get(f"products/{product_id}")

        if not isinstance(response.data, dict):
            msg = (
                f"Expected dict response for product {product_id}, "
                f"got {type(response.data).__name__}"
            )
            raise ResponseParseError(msg)

        return Product.from_woocommerce(response.data)

    def search_products(
        self,
        query: str,
        page: int = 1,
        per_page: int = 10,
        status: str | None = None,
    ) -> PaginatedResult[Product]:
        """Search products using WooCommerce native text search parameter.

        Issues GET /products?search=<query>.
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

        response = self._client.get("products", params=params)

        if not isinstance(response.data, list):
            raise ResponseParseError(
                f"Expected list response for product search, got {type(response.data).__name__}"
            )

        items = [Product.from_woocommerce(p) for p in response.data if isinstance(p, dict)]
        return PaginatedResult.create(
            items=items,
            page=page,
            per_page=per_page,
            total_count=response.total_count,
            total_pages=response.total_pages,
        )

    def get_product_by_sku(self, sku: str) -> Product | None:
        """Perform exact SKU lookup using WooCommerce `sku=` query parameter.

        Issues GET /products?sku=<sku>.
        Returns:
            - Product if exactly one match exists
            - None if zero matches exist
        Raises:
            - InvalidInputError if sku is empty
            - ResponseParseError if more than one match is returned
        """
        if not isinstance(sku, str) or not sku.strip():
            raise InvalidInputError("sku must be a non-empty string")

        cleaned_sku = sku.strip()
        response = self._client.get("products", params={"sku": cleaned_sku})

        if not isinstance(response.data, list):
            raise ResponseParseError(
                f"Expected list response for SKU lookup, got {type(response.data).__name__}"
            )

        count = len(response.data)
        if count == 0:
            return None
        elif count == 1:
            first = response.data[0]
            if not isinstance(first, dict):
                raise ResponseParseError("Expected dict item in SKU lookup response")
            return Product.from_woocommerce(first)
        else:
            raise ResponseParseError(
                f"Unexpected multiple products ({count}) returned for exact SKU '{cleaned_sku}'. "
                "WooCommerce SKU lookups must be unique."
            )
