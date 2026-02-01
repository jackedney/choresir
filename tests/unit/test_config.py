"""Tests for configuration validation."""

import pytest

from src.core.config import Settings


def test_require_credential_with_valid_value():
    """Test require_credential returns value when credential is set."""
    settings = Settings(house_code="TEST123", house_password="secret")

    result = settings.require_credential("house_code", "House code")

    assert result == "TEST123"

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


def test_require_waha_webhook_hmac_key():
    """Test require_credential validates waha_webhook_hmac_key."""
    settings = Settings(waha_webhook_hmac_key="secret123")

    result = settings.require_credential("waha_webhook_hmac_key", "WAHA Webhook HMAC")

    assert result == "secret123"


def test_require_waha_webhook_hmac_key_missing():
    """Test require_credential raises error when waha_webhook_hmac_key is missing."""
    settings = Settings(waha_webhook_hmac_key=None)

    with pytest.raises(ValueError, match="WAHA Webhook HMAC credential not configured"):
        settings.require_credential("waha_webhook_hmac_key", "WAHA Webhook HMAC")


def test_require_waha_webhook_hmac_key_empty():
    """Test require_credential raises error when waha_webhook_hmac_key is empty string."""
    settings = Settings(waha_webhook_hmac_key="")

    with pytest.raises(ValueError, match="WAHA Webhook HMAC credential not configured"):
        settings.require_credential("waha_webhook_hmac_key", "WAHA Webhook HMAC")
