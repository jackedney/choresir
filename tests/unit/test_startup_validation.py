"""Tests for startup validation functions."""

from unittest.mock import patch

import pytest

from src.core.config import Settings
from src.main import validate_startup_configuration


# Legacy credential validation tests
def test_startup_fails_without_house_code() -> None:
    """Test that application startup fails when house_code is missing."""
    settings = Settings(house_code=None, house_password="test_password")
    with pytest.raises(ValueError, match="House onboarding code credential not configured"):
        settings.require_credential("house_code", "House onboarding code")


def test_startup_fails_without_house_password() -> None:
    """Test that application startup fails when house_password is missing."""
    settings = Settings(house_code="TEST123", house_password=None)
    with pytest.raises(ValueError, match="House onboarding password credential not configured"):
        settings.require_credential("house_password", "House onboarding password")


def test_startup_fails_with_empty_house_code() -> None:
    """Test that application startup fails when house_code is empty string."""
    settings = Settings(house_code="", house_password="test_password")
    with pytest.raises(ValueError, match="House onboarding code credential not configured"):
        settings.require_credential("house_code", "House onboarding code")


def test_startup_succeeds_with_valid_credentials() -> None:
    """Test that validation passes when both credentials are properly set."""
    settings = Settings(house_code="TEST123", house_password="test_password")
    house_code = settings.require_credential("house_code", "House onboarding code")
    house_password = settings.require_credential("house_password", "House onboarding password")
    assert house_code == "TEST123"
    assert house_password == "test_password"


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
