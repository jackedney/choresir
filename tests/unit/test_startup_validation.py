"""Tests for startup validation functions."""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.main import (
    check_pocketbase_connectivity,
    check_redis_connectivity,
    validate_startup_configuration,
)


# Legacy credential validation tests
def test_startup_fails_without_house_code() -> None:
    """Test that application startup fails when house_code is missing."""
    settings = Settings(house_code=None, house_password="test_password", waha_webhook_hmac_key="test123")
    with pytest.raises(ValueError, match="House onboarding code credential not configured"):
        settings.require_credential("house_code", "House onboarding code")


def test_startup_fails_without_house_password() -> None:
    """Test that application startup fails when house_password is missing."""
    settings = Settings(house_code="TEST123", house_password=None, waha_webhook_hmac_key="test123")
    with pytest.raises(ValueError, match="House onboarding password credential not configured"):
        settings.require_credential("house_password", "House onboarding password")


def test_startup_fails_without_waha_webhook_hmac_key() -> None:
    """Test that application startup fails when waha_webhook_hmac_key is missing."""

    # Temporarily unset the environment variable
    original_value = os.environ.pop("WAHA_WEBHOOK_HMAC_KEY", None)
    try:
        with pytest.raises(ValidationError, match=r"waha_webhook_hmac_key"):
            Settings()  # type: ignore[arg-type]
    finally:
        # Restore the original value
        if original_value is not None:
            os.environ["WAHA_WEBHOOK_HMAC_KEY"] = original_value


def test_startup_fails_with_empty_house_code() -> None:
    """Test that application startup fails when house_code is empty string."""
    settings = Settings(house_code="", house_password="test_password", waha_webhook_hmac_key="test123")
    with pytest.raises(ValueError, match="House onboarding code credential not configured"):
        settings.require_credential("house_code", "House onboarding code")


def test_startup_succeeds_with_valid_credentials() -> None:
    """Test that validation passes when both credentials are properly set."""
    settings = Settings(house_code="TEST123", house_password="test_password", waha_webhook_hmac_key="secret123")
    waha_webhook_hmac_key = settings.require_credential("waha_webhook_hmac_key", "WAHA Webhook HMAC")
    house_code = settings.require_credential("house_code", "House onboarding code")
    house_password = settings.require_credential("house_password", "House onboarding password")
    assert waha_webhook_hmac_key == "secret123"
    assert house_code == "TEST123"
    assert house_password == "test_password"


# New comprehensive startup validation tests
@pytest.mark.asyncio
async def test_check_pocketbase_connectivity_success() -> None:
    """Test successful PocketBase connectivity check."""
    mock_client = Mock()
    mock_client.auth_store.token = "test_token"

    with patch("src.main.get_client", return_value=mock_client):
        await check_pocketbase_connectivity()


@pytest.mark.asyncio
async def test_check_pocketbase_connectivity_no_token() -> None:
    """Test PocketBase connectivity check fails when no token present."""
    mock_client = Mock()
    mock_client.auth_store.token = None

    with (
        patch("src.main.get_client", return_value=mock_client),
        pytest.raises(ConnectionError, match="PocketBase connectivity check failed"),
    ):
        await check_pocketbase_connectivity()


@pytest.mark.asyncio
async def test_check_redis_connectivity_disabled() -> None:
    """Test Redis check when Redis is not configured."""
    mock_redis = Mock()
    mock_redis.is_available = False

    with patch("src.main.redis_client", mock_redis):
        await check_redis_connectivity()


@pytest.mark.asyncio
async def test_check_redis_connectivity_success() -> None:
    """Test successful Redis connectivity check."""
    mock_redis = Mock()
    mock_redis.is_available = True
    mock_redis.ping = AsyncMock(return_value=True)

    with patch("src.main.redis_client", mock_redis):
        await check_redis_connectivity()
        mock_redis.ping.assert_called_once()


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


@pytest.mark.asyncio
async def test_validate_startup_configuration_service_unreachable() -> None:
    """Test validation fails and exits when service is unreachable."""

    async def mock_check_pocketbase() -> None:
        raise ConnectionError("PocketBase unreachable")

    with (
        patch("src.main.settings") as mock_settings,
        patch("src.main.check_pocketbase_connectivity", side_effect=mock_check_pocketbase),
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_settings.require_credential.return_value = "test_value"
        await validate_startup_configuration()

    exc = exc_info.value
    assert isinstance(exc, SystemExit)
    assert exc.code == 1
