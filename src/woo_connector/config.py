"""Configuration for WooCommerce connector with security validation."""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from woo_connector.errors import WooCommerceConfigError


class WooCommerceConfig(BaseSettings):
    """Connector configuration validated against security policies."""

    model_config = SettingsConfigDict(
        env_prefix="WOO_",
        extra="ignore",
        populate_by_name=True,
    )

    base_url: str = Field(
        ...,
        alias="base_url",
        description="Base URL for WooCommerce REST API (e.g. https://store.com/wp-json/wc/v3)",
    )
    consumer_key: str = Field(
        ...,
        alias="consumer_key",
        description="WooCommerce REST API Consumer Key",
    )
    consumer_secret: SecretStr = Field(
        ...,
        alias="consumer_secret",
        description="WooCommerce REST API Consumer Secret",
    )
    allow_insecure_http: bool = Field(
        default=False,
        alias="allow_insecure_http",
        description="Permit plain HTTP connections (DEVELOPMENT ONLY)",
    )
    timeout_seconds: float = Field(
        default=15.0,
        alias="timeout_seconds",
        ge=1.0,
        le=120.0,
        description="Request timeout in seconds",
    )

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        cleaned = v.strip().rstrip("/")
        if not cleaned:
            raise WooCommerceConfigError("WOO_BASE_URL cannot be empty")
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            raise WooCommerceConfigError("WOO_BASE_URL must begin with http:// or https://")
        if not cleaned.endswith("/wp-json/wc/v3"):
            cleaned = f"{cleaned}/wp-json/wc/v3"
        return cleaned

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        # Enforce security policy: HTTPS required unless explicitly allowed for local dev
        if self.base_url.startswith("http://") and not self.allow_insecure_http:
            raise WooCommerceConfigError(
                "Insecure HTTP is disabled by default for production security. "
                "Set WOO_ALLOW_INSECURE_HTTP=true ONLY for local development over HTTP."
            )

    @property
    def secret_value(self) -> str:
        """Helper to safely unwrap consumer secret."""
        return self.consumer_secret.get_secret_value()


class SeedConfig(BaseSettings):
    """Configuration for WooCommerce store seeding operations requiring write access."""

    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    base_url: str = Field(
        default="",
        validation_alias="WOO_BASE_URL",
        description="Base URL for WooCommerce REST API",
    )
    seed_consumer_key: str = Field(
        default="",
        validation_alias="WOO_SEED_CONSUMER_KEY",
        description="Dedicated write-capable WooCommerce Consumer Key",
    )
    seed_consumer_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="WOO_SEED_CONSUMER_SECRET",
        description="Dedicated write-capable WooCommerce Consumer Secret",
    )
    allow_insecure_http: bool = Field(
        default=False,
        validation_alias="WOO_ALLOW_INSECURE_HTTP",
        description="Permit plain HTTP connections (DEVELOPMENT ONLY)",
    )
    seed_enabled: bool = Field(
        default=False,
        validation_alias="SEED_WOOCOMMERCE",
        description="Explicit safety confirmation flag required before writes",
    )
    timeout_seconds: float = Field(
        default=15.0,
        validation_alias="WOO_TIMEOUT_SECONDS",
        ge=1.0,
        le=120.0,
    )

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        cleaned = v.strip().rstrip("/")
        if not cleaned:
            return ""
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            raise WooCommerceConfigError("WOO_BASE_URL must begin with http:// or https://")
        if not cleaned.endswith("/wp-json/wc/v3"):
            cleaned = f"{cleaned}/wp-json/wc/v3"
        return cleaned

    def validate_seed_preconditions(self) -> None:
        """Ensure all required environment variables and safety gates are satisfied."""
        if not self.seed_enabled:
            raise WooCommerceConfigError(
                "Seeding is disabled by default. Set SEED_WOOCOMMERCE=1 to explicitly permit "
                "creating fictional data in the configured WooCommerce store."
            )
        if not self.base_url:
            raise WooCommerceConfigError("WOO_BASE_URL must be specified for seeding")
        if not self.seed_consumer_key:
            raise WooCommerceConfigError(
                "WOO_SEED_CONSUMER_KEY must be specified. "
                "The normal read-only WOO_CONSUMER_KEY must not be used for seeding."
            )
        if not self.seed_consumer_secret.get_secret_value():
            raise WooCommerceConfigError(
                "WOO_SEED_CONSUMER_SECRET must be specified. "
                "The normal read-only WOO_CONSUMER_SECRET must not be used for seeding."
            )
        if self.base_url.startswith("http://") and not self.allow_insecure_http:
            raise WooCommerceConfigError(
                "Insecure HTTP is disabled by default for production security. "
                "Set WOO_ALLOW_INSECURE_HTTP=true ONLY for local development over HTTP."
            )

    def to_client_config(self) -> WooCommerceConfig:
        """Create a validated WooCommerceConfig for the shared WooCommerceClient."""
        self.validate_seed_preconditions()
        return WooCommerceConfig(
            base_url=self.base_url,
            consumer_key=self.seed_consumer_key,
            consumer_secret=self.seed_consumer_secret,
            allow_insecure_http=self.allow_insecure_http,
            timeout_seconds=self.timeout_seconds,
        )
