"""Tests for retry calculations, Retry-After parsing, jitter, and budget."""

from datetime import UTC, datetime

from woo_connector.retry import RetryPolicy, parse_retry_after


def test_parse_retry_after_seconds() -> None:
    assert parse_retry_after("15") == 15.0
    assert parse_retry_after("0") == 0.0
    assert parse_retry_after(" 42.5 ") == 42.5


def test_parse_retry_after_http_date() -> None:
    # Target date: 10 seconds ahead
    now = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
    http_date = "Mon, 05 Oct 2026 12:00:10 GMT"
    parsed = parse_retry_after(http_date, now=now)
    assert parsed == 10.0


def test_parse_retry_after_past_http_date_returns_zero() -> None:
    now = datetime(2026, 10, 5, 12, 0, 10, tzinfo=UTC)
    http_date = "Mon, 05 Oct 2026 12:00:00 GMT"
    parsed = parse_retry_after(http_date, now=now)
    assert parsed == 0.0


def test_parse_retry_after_invalid_fallback() -> None:
    assert parse_retry_after("invalid_header") is None
    assert parse_retry_after("") is None
    assert parse_retry_after(None) is None


def test_retry_after_capped_at_max() -> None:
    policy = RetryPolicy(max_retry_after=30.0)
    delay = policy.compute_delay(attempt=0, retry_after=120.0)
    assert delay == 30.0


def test_exponential_backoff_progression() -> None:
    policy = RetryPolicy(backoff_factor=1.0, jitter=False, max_retry_after=30.0)
    assert policy.compute_delay(0) == 1.0
    assert policy.compute_delay(1) == 2.0
    assert policy.compute_delay(2) == 4.0
    assert policy.compute_delay(3) == 8.0


def test_jitter_bounds() -> None:
    policy = RetryPolicy(backoff_factor=1.0, jitter=True)
    delays = [policy.compute_delay(0) for _ in range(50)]
    for d in delays:
        assert 0.8 <= d <= 1.2
