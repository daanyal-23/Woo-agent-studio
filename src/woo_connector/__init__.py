"""WooCommerce private connector package foundation."""

from woo_connector.client import WooCommerceClient, WooCommerceResponse
from woo_connector.config import SeedConfig, WooCommerceConfig
from woo_connector.errors import (
    AuthenticationError,
    BadRequestError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitExceededError,
    ResponseParseError,
    ServerError,
    WooCommerceAPIError,
    WooCommerceConfigError,
    WooCommerceError,
    WooCommerceTransportError,
)
from woo_connector.models import Order, OrderLineItem, PaginatedResult, Product
from woo_connector.orders import OrderService
from woo_connector.products import ProductService
from woo_connector.retry import RetryPolicy

__all__ = [
    "AuthenticationError",
    "BadRequestError",
    "InvalidInputError",
    "NotFoundError",
    "Order",
    "OrderLineItem",
    "OrderService",
    "PaginatedResult",
    "PermissionDeniedError",
    "Product",
    "ProductService",
    "RateLimitExceededError",
    "ResponseParseError",
    "RetryPolicy",
    "SeedConfig",
    "ServerError",
    "WooCommerceAPIError",
    "WooCommerceClient",
    "WooCommerceConfig",
    "WooCommerceConfigError",
    "WooCommerceError",
    "WooCommerceResponse",
    "WooCommerceTransportError",
]
