"""Retry, backoff, and jitter policy with testable sleep injection."""

import email.utils
import random
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def parse_retry_after(header_value: str | None, now: datetime | None = None) -> float | None:
    """Parse Retry-After header in seconds or HTTP-date format.

    Returns float seconds if valid, or None if missing or unparseable.
    """
    if not header_value:
        return None

    cleaned = header_value.strip()

    # 1. Try integer/float seconds
    try:
        val = float(cleaned)
        if val >= 0:
            return val
    except ValueError:
        pass

    # 2. Try HTTP-date format (RFC 7231 / RFC 2822)
    try:
        parsed_dt = email.utils.parsedate_to_datetime(cleaned)
        if parsed_dt is not None:
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=UTC)
            current_dt = now or datetime.now(UTC)
            delta = (parsed_dt - current_dt).total_seconds()
            return max(0.0, delta)
    except (ValueError, TypeError):
        pass

    # Invalid format falls back to standard exponential backoff
    return None


class RetryPolicy(BaseModel):
    """Retry configuration with exponential backoff, jitter, and safety limits."""

    max_retries: int = Field(default=3, ge=0)
    backoff_factor: float = Field(default=0.5, ge=0.0)
    jitter: bool = True
    max_retry_after: float = Field(default=30.0, ge=1.0)
    total_timeout_budget: float = Field(default=60.0, ge=1.0)
    sleep_fn: Any = Field(default=time.sleep, exclude=True)

    def compute_delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Compute sleep duration honoring Retry-After cap and exponential backoff."""
        if retry_after is not None:
            # Honor Retry-After capped to max_retry_after
            return min(max(0.0, retry_after), self.max_retry_after)

        # Standard exponential backoff: factor * 2^attempt
        delay = self.backoff_factor * (2**attempt)
        if self.jitter:
            delay = delay * random.uniform(0.8, 1.2)

        return min(delay, self.max_retry_after)

    def sleep(self, seconds: float) -> None:
        """Invoke injectable sleep callable."""
        self.sleep_fn(seconds)
