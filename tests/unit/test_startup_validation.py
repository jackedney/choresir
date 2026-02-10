"""Tests for startup validation functions."""

from unittest.mock import patch

import pytest

from src.core.config import Settings
from src.main import validate_startup_configuration


# Credential validation tests
def test_startup_fails_without_openrouter_api_key() -> None:
    """Test that application startup fails when openrouter_api_key is missing."""
    settings = Settings(openrouter_api_key=None)
    with pytest.raises(ValueError, match="OpenRouter API key credential not configured"):
        settings.require_credential("openrouter_api_key", "OpenRouter API key")


def test_startup_fails_with_empty_openrouter_api_key() -> None:
    """Test that application startup fails when openrouter_api_key is empty string."""
    settings = Settings(openrouter_api_key="")
    with pytest.raises(ValueError, match="OpenRouter API key credential not configured"):
        settings.require_credential("openrouter_api_key", "OpenRouter API key")


def test_startup_succeeds_with_valid_credentials() -> None:
    """Test that validation passes when credentials are properly set."""
    settings = Settings(openrouter_api_key="sk-test-123", admin_password="secret")
    api_key = settings.require_credential("openrouter_api_key", "OpenRouter API key")
    admin_pwd = settings.require_credential("admin_password", "Admin password")
    assert api_key == "sk-test-123"
    assert admin_pwd == "secret"


@pytest.mark.asyncio
async def test_validate_startup_configuration_missing_credential() -> None:
    """Test validation fails and exits when credential is missing."""

    def mock_require_credential(field: str, name: str) -> str:
        if field == "openrouter_api_key":
            raise ValueError(f"{name} credential not configured")
        return "test_value"

    with (
        patch("src.main.settings") as mock_settings,
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_settings.require_credential.side_effect = mock_require_credential
        await validate_startup_configuration()

    exc = exc_info.value
    assert isinstance(exc, SystemExit)
    assert exc.code == 1
