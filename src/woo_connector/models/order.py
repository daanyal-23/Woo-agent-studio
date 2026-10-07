"""Normalized Order domain model for WooCommerce connector with strict PII minimization."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from woo_connector.models.normalization import clean_text, mask_email

KNOWN_ORDER_STATUSES = frozenset(
    {"pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed", "trash"}
)


class OrderLineItem(BaseModel):
    """Lean representation of an order line item."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="Line item ID")
    product_id: int | None = Field(default=None, description="Associated product ID")
    name: str = Field(description="Product or service name at purchase")
    sku: str = Field(default="", description="Product SKU if recorded")
    quantity: int = Field(default=1, description="Purchased quantity")
    subtotal: str = Field(default="0.00", description="Line subtotal before discount")
    total: str = Field(default="0.00", description="Line total after discount")

    @classmethod
    def from_woocommerce(cls, data: dict[str, Any]) -> "OrderLineItem":
        """Construct a normalized line item from a WooCommerce line item dict."""
        return cls(
            id=int(data.get("id") or 0),
            product_id=data.get("product_id"),
            name=clean_text(str(data.get("name") or "Item"), max_length=200),
            sku=str(data.get("sku") or "").strip(),
            quantity=int(data.get("quantity") or 1),
            subtotal=str(data.get("subtotal") or "0.00"),
            total=str(data.get("total") or "0.00"),
        )


class Order(BaseModel):
    """Normalized, PII-minimized Order entity.

    Excludes raw customer emails, physical addresses, telephone numbers,
    and private customer notes.
    """

    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="Unique WooCommerce order ID")
    status: str = Field(description="Order lifecycle status")
    currency: str = Field(default="INR", description="Currency ISO code")
    total: str = Field(default="0.00", description="Total order amount charged")
    total_tax: str = Field(default="0.00", description="Tax amount included or applied")
    refund_total: str = Field(default="0.00", description="Sum of refunded amounts on this order")
    payment_method: str = Field(
        default="", description="Payment gateway identifier (e.g. razorpay)"
    )
    payment_method_title: str = Field(default="", description="Human-friendly payment method title")
    transaction_id: str = Field(default="", description="Payment gateway transaction/charge ID")
    date_created: str | None = Field(default=None, description="Order creation timestamp")
    date_paid: str | None = Field(default=None, description="Payment completion timestamp")
    customer_name: str = Field(default="", description="Customer first and last name")
    customer_email_masked: str | None = Field(
        default=None,
        description="Masked customer email (PII minimized, e.g. 'j***e@example.com')",
    )
    line_items: list[OrderLineItem] = Field(default_factory=list, description="Order line items")
    seed_id: str | None = Field(
        default=None,
        description="Deterministic seed identifier extracted from _seed_id metadata if present",
    )

    @field_validator("status", mode="before")
    @classmethod
    def validate_or_fallback_status(cls, v: Any) -> str:
        """Tolerantly accept known statuses, falling back to clean lowercase string."""
        if not v:
            return "pending"
        val_str = str(v).strip().lower()
        return val_str

    @classmethod
    def from_woocommerce(cls, data: dict[str, Any]) -> "Order":
        """Factory to construct a normalized, PII-minimized Order from a raw WooCommerce dict."""
        billing = data.get("billing") or {}
        first_name = str(billing.get("first_name") or "").strip()
        last_name = str(billing.get("last_name") or "").strip()
        customer_name = f"{first_name} {last_name}".strip()

        # Mask email immediately during extraction; raw email is NEVER retained
        raw_email = billing.get("email")
        masked_email = mask_email(raw_email) if raw_email else None

        # Parse line items
        raw_items = data.get("line_items") or []
        parsed_items = [
            OrderLineItem.from_woocommerce(item) for item in raw_items if isinstance(item, dict)
        ]

        # Extract deterministic seed_id from meta_data if present
        seed_id: str | None = None
        for meta in data.get("meta_data") or []:
            if isinstance(meta, dict) and meta.get("key") == "_seed_id":
                val = meta.get("value")
                if val:
                    seed_id = str(val).strip()
                    break

        # Calculate or extract refund total
        refund_total = "0.00"
        refunds = data.get("refunds") or []
        if refunds:
            try:
                total_refund_float = sum(
                    abs(float(r.get("total") or 0.0)) for r in refunds if isinstance(r, dict)
                )
                refund_total = f"{total_refund_float:.2f}"
            except (ValueError, TypeError):
                refund_total = "0.00"
        elif "refund_total" in data:
            refund_total = str(data["refund_total"])
        else:
            # Check meta_data for custom _refund_amount if recorded during seed
            for meta in data.get("meta_data") or []:
                if isinstance(meta, dict) and meta.get("key") == "_refund_amount":
                    refund_total = str(meta.get("value") or "0.00")
                    break

        return cls(
            id=int(data.get("id") or 0),
            status=str(data.get("status") or "pending"),
            currency=str(data.get("currency") or "INR").upper(),
            total=str(data.get("total") or "0.00"),
            total_tax=str(data.get("total_tax") or "0.00"),
            refund_total=refund_total,
            payment_method=str(data.get("payment_method") or "").strip(),
            payment_method_title=str(data.get("payment_method_title") or "").strip(),
            transaction_id=str(data.get("transaction_id") or "").strip(),
            date_created=data.get("date_created") or data.get("date_created_gmt"),
            date_paid=data.get("date_paid") or data.get("date_paid_gmt"),
            customer_name=customer_name,
            customer_email_masked=masked_email,
            line_items=parsed_items,
            seed_id=seed_id,
        )
