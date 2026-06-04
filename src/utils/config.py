"""
Configuration management for AAP MCP Server.
All settings are loaded from environment variables with sensible defaults.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AAP MCP Server configuration."""

    model_config = SettingsConfigDict(
        env_prefix="AAP_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    # AAP Controller connection
    aap_controller_url: str = Field(
        default="",
        description="AAP Controller base URL (e.g. https://controller.example.com)",
        alias="AAP_CONTROLLER_URL",
    )
    aap_api_base_path: str = Field(
        default="/api/v2",
        description="AAP API base path (e.g. /api/controller/v2)",
        alias="AAP_API_BASE_PATH",
    )
    aap_username: str | None = Field(
        default=None,
        description="AAP username for basic auth (use oauth_token instead)",
        alias="AAP_USERNAME",
    )
    aap_password: str | None = Field(
        default=None,
        description="AAP password for basic auth",
        alias="AAP_PASSWORD",
    )
    aap_oauth_token: str | None = Field(
        default=None,
        description="AAP OAuth2 token (preferred over username/password)",
        alias="AAP_OAUTH_TOKEN",
    )
    aap_verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates",
        alias="AAP_VERIFY_SSL",
    )

    # Server behavior
    read_only_mode: bool = Field(
        default=False,
        description="When True, block all write/delete operations",
    )
    require_confirmation: bool = Field(
        default=True,
        description="Require explicit confirmation tokens for destructive operations",
    )
    max_page_size: int = Field(
        default=200,
        description="Maximum page size for list operations",
        ge=1,
        le=1000,
    )

    # HTTP client settings
    request_timeout_seconds: float = Field(default=60.0, ge=1.0)
    max_connections: int = Field(default=20, ge=1)
    max_keepalive_connections: int = Field(default=10, ge=1)

    # Rate limiting
    rate_limit_requests_per_minute: int = Field(default=120, ge=1)

    # Audit logging
    audit_log_file: str | None = Field(
        default="/var/log/aap-mcp/audit.jsonl",
        description="Path for structured audit log. None disables file logging.",
    )

    # MCP transport
    mcp_transport: str = Field(default="streamable_http")
    mcp_port: int = Field(default=8000, ge=1, le=65535)
    mcp_host: str = Field(default="0.0.0.0")

    @field_validator("aap_controller_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("aap_oauth_token", "aap_password", mode="before")
    @classmethod
    def mask_secrets(cls, v):
        # Secrets are stored as-is; masking happens in audit logger
        return v
