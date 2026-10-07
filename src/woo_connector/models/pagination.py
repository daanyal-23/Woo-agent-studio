"""Generic pagination model for connector list and search operations."""

from pydantic import BaseModel, ConfigDict, Field


class PaginatedResult[T](BaseModel):
    """Immutable paginated collection contract returned by connector services."""

    model_config = ConfigDict(frozen=True)

    items: list[T] = Field(default_factory=list, description="Items on current page")
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    per_page: int = Field(ge=1, description="Number of items requested per page")
    total_count: int | None = Field(
        default=None,
        description="Total item count from X-WP-Total header, or None if missing",
    )
    total_pages: int | None = Field(
        default=None,
        description="Total page count from X-WP-TotalPages header, or None if missing",
    )
    has_more: bool = Field(
        default=False,
        description="Whether additional pages exist beyond the current page",
    )
    next_page: int | None = Field(
        default=None,
        description="Next 1-indexed page number if has_more is True, else None",
    )

    @classmethod
    def create(
        cls,
        items: list[T],
        page: int,
        per_page: int,
        total_count: int | None,
        total_pages: int | None,
    ) -> "PaginatedResult[T]":
        """Deterministic factory adhering strictly to WooCommerce pagination header semantics.

        Rule:
        - If X-WP-TotalPages is present:
            has_more = page < total_pages
            next_page = page + 1 if has_more else None
        - If pagination headers are missing:
            has_more = False
            next_page = None
        """
        if total_pages is not None:
            has_more = page < total_pages
            next_page = (page + 1) if has_more else None
        else:
            has_more = False
            next_page = None

        return cls(
            items=items,
            page=page,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            has_more=has_more,
            next_page=next_page,
        )
