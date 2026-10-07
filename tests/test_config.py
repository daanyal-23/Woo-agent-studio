"""Tests for configuration parsing and security rules."""

import pytest
from pydantic import ValidationError

from woo_connector.config import WooCommerceConfig
from woo_connector.errors import WooCommerceConfigError


def test_valid_https_configuration() -> None:
    config = WooCommerceConfig(
        base_url="https://example.com/wp-json/wc/v3/",
        consumer_key="ck_key",
        consumer_secret="cs_secret",
    )
    assert config.base_url == "https://example.com/wp-json/wc/v3"
    assert config.consumer_key == "ck_key"
    assert config.secret_value == "cs_secret"
    assert config.allow_insecure_http is False
    assert config.timeout_seconds == 15.0


def test_insecure_http_rejected_by_default() -> None:
    with pytest.raises(WooCommerceConfigError) as exc_info:
        WooCommerceConfig(
            base_url="http://example.com/wp-json/wc/v3",
            consumer_key="ck_key",
            consumer_secret="cs_secret",
        )
    assert "Insecure HTTP is disabled by default" in str(exc_info.value)


def test_insecure_http_allowed_when_explicitly_configured() -> None:
    config = WooCommerceConfig(
        base_url="http://localhost:8080/wp-json/wc/v3",
        consumer_key="ck_key",
        consumer_secret="cs_secret",
        allow_insecure_http=True,
    )
    assert config.base_url == "http://localhost:8080/wp-json/wc/v3"
    assert config.allow_insecure_http is True


def test_invalid_url_scheme() -> None:
    with pytest.raises(WooCommerceConfigError) as exc_info:
        WooCommerceConfig(
            base_url="ftp://example.com",
            consumer_key="ck_key",
            consumer_secret="cs_secret",
        )
    assert "must begin with http:// or https://" in str(exc_info.value)


def test_credentials_masked_in_repr() -> None:
    config = WooCommerceConfig(
        base_url="https://example.com/wp-json/wc/v3",
        consumer_key="ck_sensitive_key",
        consumer_secret="cs_sensitive_secret",
    )
    repr_str = repr(config)
    assert "cs_sensitive_secret" not in repr_str
    assert "**********" in repr_str


def test_missing_required_fields_fails() -> None:
    with pytest.raises(ValidationError):
        WooCommerceConfig.model_validate({})


def test_base_url_normalization_variants() -> None:
    """Condition 1: Base URLs without or with /wp-json/wc/v3 resolve without doubling."""
    variants = [
        "http://localhost:8080",
        "http://localhost:8080/",
        "http://localhost:8080/wp-json/wc/v3",
        "http://localhost:8080/wp-json/wc/v3/",
    ]
    expected = "http://localhost:8080/wp-json/wc/v3"

    for url in variants:
        cfg = WooCommerceConfig(
            base_url=url,
            consumer_key="ck_test",
            consumer_secret="cs_test",
            allow_insecure_http=True,
        )
        assert cfg.base_url == expected
