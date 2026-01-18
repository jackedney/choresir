"""Configuration management for choresir."""

from pathlib import Path

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

    # Twilio Configuration
    twilio_account_sid: str | None = Field(default=None, description="Twilio Account SID")
    twilio_auth_token: str | None = Field(default=None, description="Twilio Auth Token")
    twilio_whatsapp_number: str = Field(
        default="whatsapp:+14155238886", description="Twilio WhatsApp number (format: whatsapp:+14155238886)"
    )

    # Pydantic Logfire Configuration (optional)
    logfire_token: str | None = Field(default=None, description="Pydantic Logfire token for observability")

    # House Onboarding Configuration
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

    # Twilio Content API Template SIDs (optional - set after creating templates in Twilio Console)
    template_chore_reminder_sid: str | None = Field(default=None, description="Content SID for chore reminder template")
    template_verification_request_sid: str | None = Field(
        default=None, description="Content SID for verification request template"
    )
    template_conflict_notification_sid: str | None = Field(
        default=None, description="Content SID for conflict notification template"
    )

    # Admin Notification Configuration
    enable_admin_notifications: bool = Field(
        default=True, description="Enable/disable admin notifications for critical errors"
    )
    admin_notification_cooldown_minutes: int = Field(
        default=60, description="Cooldown period between notifications for the same error category (in minutes)"
    )


# Application Constants
class Constants:
    """Application-wide constants."""

    # API Configuration
    API_TIMEOUT_SECONDS: int = 30
    WHATSAPP_WEBHOOK_TIMEOUT_SECONDS: int = 3

    # HTTP Status Codes
    HTTP_OK: int = 200
    HTTP_BAD_REQUEST: int = 400
    HTTP_SERVER_ERROR: int = 500

    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE: int = 60
    MAX_AGENT_CALLS_PER_USER_PER_HOUR: int = 50

    # Scheduler Configuration
    DAILY_REMINDER_HOUR: int = 8  # 8am
    DAILY_REPORT_HOUR: int = 21  # 9pm
    WEEKLY_REPORT_HOUR: int = 20  # 8pm Sunday
    WEEKLY_REPORT_DAY: int = 6  # Sunday (0=Monday, 6=Sunday)

    # WhatsApp Message Window
    WHATSAPP_MESSAGE_WINDOW_HOURS: int = 24

    # Paths
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
    POCKETBASE_DATA_DIR: Path = PROJECT_ROOT / "pb_data"


def get_settings() -> Settings:
    """Get application settings (singleton pattern)."""
    return Settings()


# Global settings instance
settings = get_settings()
constants = Constants()
