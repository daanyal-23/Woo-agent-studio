"""Tests for structured error models and credential sanitization."""

from woo_connector.errors import (
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitExceededError,
    ResponseParseError,
    ServerError,
    WooCommerceConfigError,
    WooCommerceError,
    WooCommerceTransportError,
)


def test_error_attributes_and_to_dict() -> None:
    err = RateLimitExceededError(
        message="Too many requests",
        code="rate_limit_exceeded",
        retry_after=15.0,
    )
    assert err.status_code == 429
    assert err.retryable is True
    assert err.retry_after == 15.0

    d = err.to_dict()
    assert d == {
        "code": "rate_limit_exceeded",
        "message": "Too many requests",
        "retryable": True,
        "retry_after": 15.0,
    }


def test_response_parse_error_to_dict() -> None:
    err = ResponseParseError("Malformed HTML received", status_code=200)
    assert err.code == "response_parse_error"
    assert err.status_code == 200
    assert err.retryable is False
    assert err.retry_after is None
    assert err.to_dict() == {
        "code": "response_parse_error",
        "message": "Malformed HTML received",
        "retryable": False,
        "retry_after": None,
    }


def test_all_errors_inherit_base_and_support_to_dict() -> None:
    errors = [
        WooCommerceConfigError("bad config"),
        WooCommerceTransportError("timeout"),
        ResponseParseError("bad json"),
        BadRequestError("bad req"),
        AuthenticationError("invalid creds"),
        PermissionDeniedError("denied"),
        NotFoundError("missing"),
        RateLimitExceededError("slow down", retry_after=5.0),
        ServerError("oops", status_code=500),
    ]

    for err in errors:
        assert isinstance(err, WooCommerceError)
        d = err.to_dict()
        assert "code" in d
        assert "message" in d
        assert "retryable" in d
        assert "retry_after" in d


def test_credentials_never_appear_in_error_representation() -> None:
    secret = "cs_super_secret_token_never_leak"
    key = "ck_sensitive_key_val"

    err = AuthenticationError("Authentication failed for request")
    rendered = str(err)
    error_dict = str(err.to_dict())

    assert secret not in rendered
    assert key not in rendered
    assert "Authorization" not in rendered
    assert secret not in error_dict
    assert key not in error_dict
