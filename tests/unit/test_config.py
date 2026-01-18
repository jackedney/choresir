"""Tests for configuration validation."""

import pytest

from src.core.config import Settings


def test_require_credential_with_valid_value():
    """Test require_credential returns value when credential is set."""
    settings = Settings(house_code="TEST123", house_password="secret")

    result = settings.require_credential("house_code", "House code")

    assert result == "TEST123"


def test_require_credential_with_none_raises_error():
    """Test require_credential raises ValueError when credential is None."""
    settings = Settings(house_code=None, house_password="secret")

    with pytest.raises(ValueError, match="House code credential not configured"):
        settings.require_credential("house_code", "House code")


def test_require_credential_with_empty_string_raises_error():
    """Test require_credential raises ValueError when credential is empty."""
    settings = Settings(house_code="", house_password="secret")

    with pytest.raises(ValueError, match="House code credential not configured"):
        settings.require_credential("house_code", "House code")


def test_require_credential_error_message_includes_field_name():
    """Test error message includes the environment variable name."""
    settings = Settings(house_password=None)

    with pytest.raises(ValueError, match="HOUSE_PASSWORD"):
        settings.require_credential("house_password", "House password")
