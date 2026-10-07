"""WooCommerce domain models package."""

from woo_connector.models.normalization import (
    clean_text,
    mask_email,
    normalize_whitespace,
    strip_html,
    truncate_text,
)
from woo_connector.models.order import Order, OrderLineItem
from woo_connector.models.pagination import PaginatedResult
from woo_connector.models.product import Product

__all__ = [
    "Order",
    "OrderLineItem",
    "PaginatedResult",
    "Product",
    "clean_text",
    "mask_email",
    "normalize_whitespace",
    "strip_html",
    "truncate_text",
]
