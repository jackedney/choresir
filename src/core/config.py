"""Configuration management for choresir."""

from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # PocketBase Configuration
    pocketbase_url: str = Field(default="http://127.0.0.1:8090", description="PocketBase server URL")
    pocketbase_admin_email: str = Field(
        default="admin@test.local", description="PocketBase admin email for schema sync"
    )
    pocketbase_admin_password: str = Field(
        default="testpassword123", description="PocketBase admin password for schema sync"
    )

    # OpenRouter Configuration
    openrouter_api_key: str | None = Field(default=None, description="OpenRouter API key for LLM access")

    # WAHA Configuration
    waha_base_url: str = Field(default="http://waha:3000", description="WAHA Base URL")
    waha_api_key: str | None = Field(default=None, description="WAHA API Key (optional)")
    waha_webhook_hmac_key: str = Field(description="WAHA Webhook HMAC key for payload validation")

    # Pydantic Logfire Configuration (optional)
    logfire_token: str | None = Field(default=None, description="Pydantic Logfire token for observability")

    # Redis Configuration (optional)
    redis_url: str | None = Field(default=None, description="Redis connection URL (e.g., redis://localhost:6379)")

    # House Onboarding Configuration
    house_name: str | None = Field(default=None, description="House name for member onboarding")
    house_code: str | None = Field(default=None, description="House code for member onboarding")
    house_password: str | None = Field(default=None, description="House password for member onboarding")

    def require_credential(self, field_name: str, service_name: str) -> str:
        """Validate that a required credential is set, raising a clear error if missing.

        Args:
            field_name: Name of the field to check
            service_name: Human-readable service name for error message

        Returns:
            The credential value

        Raises:
            ValueError: If the credential is None or empty
        """
        value = getattr(self, field_name)
        if not value:
            raise ValueError(
                f"{service_name} credential not configured. "
                f"Set {field_name.upper()} environment variable or add to .env file."
            )
        return value

    # AI Model Configuration
    model_id: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="Model ID for OpenRouter (defaults to Claude 3.5 Sonnet)",
    )

    # Admin Notification Configuration
    enable_admin_notifications: bool = Field(
        default=True, description="Enable/disable admin notifications for critical errors"
    )
    admin_notification_cooldown_minutes: int = Field(
        default=60, description="Cooldown period between notifications for the same error category (in minutes)"
    )

    # Robin Hood Protocol Configuration
    robin_hood_weekly_limit: int = Field(
        default=3, description="Maximum number of chore takeovers allowed per user per week"
    )


# Application Constants
class Constants:
    """Application-wide constants."""

    # API Configuration
    API_TIMEOUT_SECONDS: Final[int] = 30
    WHATSAPP_WEBHOOK_TIMEOUT_SECONDS: Final[int] = 3

    # HTTP Status Codes
    HTTP_OK: Final[int] = 200
    HTTP_BAD_REQUEST: Final[int] = 400
    HTTP_SERVER_ERROR: Final[int] = 500

    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE: Final[int] = 60
    MAX_AGENT_CALLS_PER_USER_PER_HOUR: Final[int] = 50

    # Webhook Security
    WEBHOOK_MAX_AGE_SECONDS: Final[int] = 300  # 5 minutes
    WEBHOOK_NONCE_TTL_SECONDS: Final[int] = 600  # 10 minutes (2x max age for safety)
    WEBHOOK_RATE_LIMIT_PER_PHONE: Final[int] = 20  # Max webhooks per phone per minute

    # Scheduler Configuration
    DAILY_REMINDER_HOUR: Final[int] = 8  # 8am
    DAILY_REPORT_HOUR: Final[int] = 21  # 9pm
    WEEKLY_REPORT_HOUR: Final[int] = 20  # 8pm Sunday
    WEEKLY_REPORT_DAY: Final[int] = 6  # Sunday (0=Monday, 6=Sunday)

    # WhatsApp Message Window
    WHATSAPP_MESSAGE_WINDOW_HOURS: Final[int] = 24

    # Cache TTLs
    CACHE_TTL_LEADERBOARD_SECONDS: Final[int] = 60  # 1 minute for leaderboard cache

    # Webhook Payload Format
    WEBHOOK_BUTTON_PAYLOAD_PARTS: Final[int] = 3  # Expected parts in button payload (e.g., "VERIFY:APPROVE:log_id")

    # Leaderboard & Gamification
    LEADERBOARD_RANK_FIRST: Final[int] = 1
    LEADERBOARD_RANK_SECOND: Final[int] = 2
    LEADERBOARD_RANK_THIRD: Final[int] = 3
    LEADERBOARD_COMPLETIONS_CARRYING_TEAM: Final[int] = 5  # Threshold for "Carrying the team!" title
    LEADERBOARD_COMPLETIONS_NEEDS_IMPROVEMENT: Final[int] = 2  # Threshold for "Room for improvement" title

    # Auto-verification
    AUTO_VERIFY_PENDING_HOURS: Final[int] = 48  # Hours before auto-verifying personal chore logs

    # Rate Limiting Windows
    RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60  # Window for webhook rate limiting (1 minute)
    RATE_LIMIT_AGENT_WINDOW_SECONDS: Final[int] = 3600  # Window for agent rate limiting (1 hour)

    # Pagination Defaults
    DEFAULT_PER_PAGE_LIMIT: Final[int] = 100  # Default pagination limit for list queries

    # Redis Configuration
    REDIS_MAX_CONNECTIONS: Final[int] = 10  # Maximum connections in Redis connection pool
    REDIS_INVALIDATION_QUEUE_MAXLEN: Final[int] = 1000  # Max items in Redis invalidation queue

    # Analytics Configuration
    ANALYTICS_CHUNK_SIZE: Final[int] = 50  # Chunk size for batch fetching analytics data

    # Job Tracker Configuration
    TRACKER_DEAD_LETTER_QUEUE_MAXLEN: Final[int] = 100  # Max items in dead letter queue
    TRACKER_CURRENT_RUN_TTL_SECONDS: Final[int] = 3600  # TTL for current job run tracking (1 hour)
    TRACKER_JOB_METRICS_TTL_SECONDS: Final[int] = 604800  # TTL for job metrics data (7 days)
    TRACKER_DEAD_LETTER_QUEUE_TTL_SECONDS: Final[int] = 2592000  # TTL for dead letter queue entries (30 days)
    TRACKER_ERROR_MESSAGE_MAX_LENGTH: Final[int] = 500  # Max length for stored error messages

    # Pagination
    DB_PER_PAGE_LARGE_LIMIT: Final[int] = 500  # Large pagination limit for bulk queries

    # Display Limits
    WHATSAPP_OVERDUE_CHORES_DISPLAY_LIMIT: Final[int] = 5  # Max overdue chores to display in WhatsApp messages
    ERROR_PREVIEW_MAX_LENGTH: Final[int] = 100  # Max length for error previews in notifications

    # Paths
    PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent.parent
    POCKETBASE_DATA_DIR: Final[Path] = PROJECT_ROOT / "pb_data"


def get_settings() -> Settings:
    """Get application settings (singleton pattern)."""
    return Settings()  # type: ignore[arg-type]


# Global settings instance
settings = get_settings()
constants = Constants()
