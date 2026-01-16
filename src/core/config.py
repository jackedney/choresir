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
    openrouter_api_key: str = Field(..., description="OpenRouter API key for LLM access")

    # WhatsApp Configuration
    whatsapp_verify_token: str = Field(..., description="WhatsApp webhook verification token")
    whatsapp_app_secret: str = Field(..., description="WhatsApp app secret for signature verification")
    whatsapp_access_token: str = Field(..., description="WhatsApp Cloud API access token")
    whatsapp_phone_number_id: str = Field(..., description="WhatsApp business phone number ID")

    # Pydantic Logfire Configuration
    logfire_token: str = Field(..., description="Pydantic Logfire token for observability")

    # House Onboarding Configuration
    house_code: str = Field(..., description="House code for member onboarding")
    house_password: str = Field(..., description="House password for member onboarding")

    # AI Model Configuration
    model_id: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="Model ID for OpenRouter (defaults to Claude 3.5 Sonnet)",
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
