"""Structured exceptions for WooCommerce connector."""

from typing import Any


class WooCommerceError(Exception):
    """Base exception for all WooCommerce connector errors."""

    def __init__(
        self,
        message: str,
        code: str = "woocommerce_error",
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after

    def to_dict(self) -> dict[str, Any]:
        """Convert error details to a standardized dictionary representation."""
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "retry_after": self.retry_after,
        }

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.status_code is not None:
            parts.append(f"(HTTP {self.status_code})")
        if self.retryable:
            parts.append("(retryable)")
        if self.retry_after is not None:
            parts.append(f"(retry_after={self.retry_after}s)")
        return " ".join(parts)


class WooCommerceConfigError(WooCommerceError):
    """Raised when connector configuration is missing or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="configuration_error",
            status_code=None,
            retryable=False,
            retry_after=None,
        )


class WooCommerceTransportError(WooCommerceError):
    """Raised when a network or transport-level timeout/connection error occurs."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="transport_error",
            status_code=None,
            retryable=True,
            retry_after=None,
        )


class ResponseParseError(WooCommerceError):
    """Raised when the server response cannot be parsed as valid JSON (e.g., HTML response)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(
            message=message,
            code="response_parse_error",
            status_code=status_code,
            retryable=False,
            retry_after=None,
        )


class WooCommerceAPIError(WooCommerceError):
    """Base exception for HTTP status code errors returned by the WooCommerce API."""

    def __init__(
        self,
        message: str,
        code: str = "api_error",
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            retryable=retryable,
            retry_after=retry_after,
        )


class BadRequestError(WooCommerceAPIError):
    """HTTP 400 Bad Request: Invalid parameters or malformed request body."""

    def __init__(self, message: str, code: str = "bad_request") -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=400,
            retryable=False,
            retry_after=None,
        )


class AuthenticationError(WooCommerceAPIError):
    """HTTP 401 Unauthorized: Invalid or missing API credentials."""

    def __init__(self, message: str, code: str = "authentication_failed") -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=401,
            retryable=False,
            retry_after=None,
        )


class PermissionDeniedError(WooCommerceAPIError):
    """HTTP 403 Forbidden: Insufficient permissions for resource."""

    def __init__(self, message: str, code: str = "permission_denied") -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=403,
            retryable=False,
            retry_after=None,
        )


class NotFoundError(WooCommerceAPIError):
    """HTTP 404 Not Found: Requested resource does not exist."""

    def __init__(self, message: str, code: str = "not_found") -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=404,
            retryable=False,
            retry_after=None,
        )


class RateLimitExceededError(WooCommerceAPIError):
    """HTTP 429 Too Many Requests: Rate limit exceeded."""

    def __init__(
        self,
        message: str,
        code: str = "rate_limit_exceeded",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=429,
            retryable=True,
            retry_after=retry_after,
        )


class ServerError(WooCommerceAPIError):
    """HTTP 5xx Server Error: Internal server error or bad gateway."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        code: str = "server_error",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            retryable=True,
            retry_after=None,
        )


class InvalidInputError(WooCommerceError, ValueError):
    """Raised when client-side parameter validation fails before sending requests."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="invalid_input",
            status_code=None,
            retryable=False,
            retry_after=None,
        )
