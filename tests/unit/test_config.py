"""Tests for configuration validation."""

import pytest

from src.core.config import Settings


def test_require_credential_with_valid_value():
    """Test require_credential returns value when credential is set."""
    settings = Settings(openrouter_api_key="sk-test-123")

    result = settings.require_credential("openrouter_api_key", "OpenRouter API key")

    assert result == "sk-test-123"


def test_require_credential_with_none_raises_error():
    """Test require_credential raises ValueError when credential is None."""
    settings = Settings(openrouter_api_key=None)

    with pytest.raises(ValueError, match="OpenRouter API key credential not configured"):
        settings.require_credential("openrouter_api_key", "OpenRouter API key")


def test_require_credential_with_empty_string_raises_error():
    """Test require_credential raises ValueError when credential is empty."""
    settings = Settings(openrouter_api_key="")

    with pytest.raises(ValueError, match="OpenRouter API key credential not configured"):
        settings.require_credential("openrouter_api_key", "OpenRouter API key")


def test_require_credential_error_message_includes_field_name():
    """Test error message includes the environment variable name."""
    settings = Settings(admin_password=None)

    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        settings.require_credential("admin_password", "Admin password")
