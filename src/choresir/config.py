"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Choresir configuration, loaded from env vars with sensible defaults."""

    model_config = {"env_prefix": "CHORESIR_"}

    # Database
    database_url: str = "sqlite+aiosqlite:///choresir.db"

    # WAHA integration
    waha_url: str = ""
    waha_api_key: str = ""
    waha_webhook_secret: str = ""

    # LLM
    openrouter_api_key: str = ""
    llm_model: str = ""

    # Admin
    admin_secret: str = ""
    admin_user: str = ""
    admin_password: str = ""

    # Rate limiting
    global_rate_limit_count: int = 20
    global_rate_limit_seconds: int = 60
    per_user_rate_limit_count: int = 5
    per_user_rate_limit_seconds: int = 60

    # Domain
    max_takeovers_per_week: int = 3
    group_chat_id: str = ""
