"""Synchronous WooCommerce HTTP client foundation."""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from woo_connector.config import WooCommerceConfig
from woo_connector.errors import (
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitExceededError,
    ResponseParseError,
    ServerError,
    WooCommerceAPIError,
    WooCommerceError,
    WooCommerceTransportError,
)
from woo_connector.retry import RetryPolicy, parse_retry_after


@dataclass(frozen=True)
class WooCommerceResponse:
    """Controlled representation of WooCommerce API responses."""

    status_code: int
    headers: dict[str, str]
    data: Any

    @property
    def total_count(self) -> int | None:
        """Parsed integer from X-WP-Total header, or None if absent/invalid."""
        val = self._find_header("x-wp-total")
        if val is not None:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    @property
    def total_pages(self) -> int | None:
        """Parsed integer from X-WP-TotalPages header, or None if absent/invalid."""
        val = self._find_header("x-wp-totalpages")
        if val is not None:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    def _find_header(self, key: str) -> str | None:
        target = key.lower()
        for k, v in self.headers.items():
            if k.lower() == target:
                return v
        return None


class WooCommerceClient:
    """Reusable synchronous WooCommerce HTTP client."""

    def __init__(
        self,
        config: WooCommerceConfig | None = None,
        base_url: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        allow_insecure_http: bool = False,
        timeout_seconds: float = 15.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            self.config = WooCommerceConfig(
                base_url=base_url or "",
                consumer_key=consumer_key or "",
                consumer_secret=consumer_secret or "",
                allow_insecure_http=allow_insecure_http,
                timeout_seconds=timeout_seconds,
            )

        self.retry_policy = retry_policy or RetryPolicy()

        # Synchronous httpx client with HTTP Basic Auth
        self._client = httpx.Client(
            auth=httpx.BasicAuth(
                username=self.config.consumer_key,
                password=self.config.secret_value,
            ),
            timeout=httpx.Timeout(self.config.timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "WooAgentConnector/0.1.0"},
        )

    def _build_url(self, endpoint: str) -> str:
        """Normalize base URL and endpoint using safe string concatenation to preserve paths."""
        base = self.config.base_url.rstrip("/")
        path = endpoint.lstrip("/")
        return f"{base}/{path}" if path else base

    def _send_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> WooCommerceResponse:
        """Execute an HTTP request with retry handling and structured error parsing."""
        url = self._build_url(endpoint)
        attempt = 0
        cumulative_sleep = 0.0

        while True:
            try:
                raw_response = self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=headers,
                )
                return self._handle_response(raw_response)

            except WooCommerceError as err:
                if not err.retryable or attempt >= self.retry_policy.max_retries:
                    raise

                delay = self.retry_policy.compute_delay(
                    attempt=attempt,
                    retry_after=err.retry_after,
                )

                if (cumulative_sleep + delay) > self.retry_policy.total_timeout_budget:
                    raise

                self.retry_policy.sleep(delay)
                cumulative_sleep += delay
                attempt += 1

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                err = WooCommerceTransportError(
                    "Transient network/transport failure contacting WooCommerce API: "
                    f"{type(exc).__name__}"
                )

                if attempt >= self.retry_policy.max_retries:
                    raise err from None

                delay = self.retry_policy.compute_delay(attempt=attempt, retry_after=None)

                if (cumulative_sleep + delay) > self.retry_policy.total_timeout_budget:
                    raise err from None

                self.retry_policy.sleep(delay)
                cumulative_sleep += delay
                attempt += 1

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> WooCommerceResponse:
        """Execute a GET request with retry handling and structured error parsing."""
        return self._send_request(
            method="GET",
            endpoint=endpoint,
            params=params,
            headers=headers,
        )

    def post(
        self,
        endpoint: str,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> WooCommerceResponse:
        """Execute a POST request with retry handling and structured error parsing."""
        return self._send_request(
            method="POST",
            endpoint=endpoint,
            params=params,
            json=json,
            headers=headers,
        )

    def _handle_response(self, response: httpx.Response) -> WooCommerceResponse:
        """Handle HTTP response, map status errors, or parse JSON."""
        status = response.status_code
        headers_dict = dict(response.headers)

        if 200 <= status < 300:
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as err:
                snippet = response.text[:120].strip()
                raise ResponseParseError(
                    (
                        f"Expected JSON response from WooCommerce, received unparseable "
                        f"content (status {status}): {snippet!r}"
                    ),
                    status_code=status,
                ) from err

            return WooCommerceResponse(
                status_code=status,
                headers=headers_dict,
                data=data,
            )

        # Non-2xx status code handling
        error_code = "api_error"
        error_message = f"WooCommerce API returned HTTP {status}"

        try:
            body_json = response.json()
            if isinstance(body_json, dict):
                error_code = str(body_json.get("code") or error_code)
                error_message = str(body_json.get("message") or error_message)
        except Exception:
            # Fallback to text snippet if body is HTML/plain text
            if response.text:
                error_message = f"{error_message}: {response.text[:120].strip()}"

        if status == 400:
            raise BadRequestError(message=error_message, code=error_code)
        elif status == 401:
            raise AuthenticationError(message=error_message, code=error_code)
        elif status == 403:
            raise PermissionDeniedError(message=error_message, code=error_code)
        elif status == 404:
            raise NotFoundError(message=error_message, code=error_code)
        elif status == 429:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitExceededError(
                message=error_message,
                code=error_code,
                retry_after=retry_after,
            )
        elif 500 <= status < 600:
            raise ServerError(message=error_message, status_code=status, code=error_code)
        else:
            raise WooCommerceAPIError(
                message=error_message,
                code=error_code,
                status_code=status,
                retryable=False,
            )

    def close(self) -> None:
        """Close underlying HTTP client session."""
        self._client.close()

    def __enter__(self) -> "WooCommerceClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
