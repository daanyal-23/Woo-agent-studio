"""Normalized Product domain model for WooCommerce connector."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from woo_connector.models.normalization import clean_text

KNOWN_PRODUCT_STATUSES = frozenset({"publish", "draft", "pending", "private"})


class Product(BaseModel):
    """Normalized, lean product entity minimizing payload size and normalizing free-text."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="Unique product identifier")
    name: str = Field(description="Human-readable product name")
    sku: str = Field(default="", description="Stock keeping unit identifier")
    price: str = Field(default="0.00", description="Current active product price")
    status: str = Field(default="publish", description="Product publication status")
    description: str = Field(
        default="",
        description="Cleaned, HTML-stripped and truncated full description",
    )
    short_description: str = Field(
        default="",
        description="Cleaned, HTML-stripped summary snippet",
    )
    stock_status: str | None = Field(default=None, description="Stock status (instock, outofstock)")
    stock_quantity: int | None = Field(default=None, description="Current stock count if tracked")
    manage_stock: bool = Field(default=False, description="Whether stock is actively tracked")
    created_at: str | None = Field(default=None, description="Creation timestamp (ISO format)")
    updated_at: str | None = Field(default=None, description="Last modification timestamp")

    @field_validator("status", mode="before")
    @classmethod
    def validate_or_fallback_status(cls, v: Any) -> str:
        """Tolerantly accept known statuses, falling back to clean lowercase string."""
        if not v:
            return "publish"
        val_str = str(v).strip().lower()
        # Allows known WooCommerce statuses or custom plugin statuses without crashing
        return val_str

    @field_validator("description", "short_description", mode="before")
    @classmethod
    def normalize_product_text(cls, v: Any) -> str:
        """Normalize free-text: strip HTML, collapse whitespace, truncate."""
        if v is None:
            return ""
        return clean_text(str(v), max_length=1000)

    @classmethod
    def from_woocommerce(cls, data: dict[str, Any]) -> "Product":
        """Factory to construct a normalized Product model from a raw WooCommerce API dictionary."""
        return cls(
            id=int(data.get("id") or 0),
            name=str(data.get("name") or "").strip(),
            sku=str(data.get("sku") or "").strip(),
            price=str(data.get("price") or data.get("regular_price") or "0.00"),
            status=str(data.get("status") or "publish"),
            description=data.get("description") or "",
            short_description=data.get("short_description") or "",
            stock_status=data.get("stock_status"),
            stock_quantity=data.get("stock_quantity"),
            manage_stock=bool(data.get("manage_stock", False)),
            created_at=data.get("date_created") or data.get("date_created_gmt"),
            updated_at=data.get("date_modified") or data.get("date_modified_gmt"),
        )
