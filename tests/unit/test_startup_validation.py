"""Tests for startup validation of required credentials."""

from unittest.mock import Mock, patch

import pytest

from src.core.config import Settings


def test_startup_fails_without_house_code():
    """Test that application startup fails when house_code is missing."""
    # Create settings with missing house_code
    settings = Settings(house_code=None, house_password="test_password")

    # Simulate the startup validation that happens in lifespan
    with pytest.raises(ValueError, match="House onboarding code credential not configured"):
        settings.require_credential("house_code", "House onboarding code")


def test_startup_fails_without_house_password():
    """Test that application startup fails when house_password is missing."""
    # Create settings with missing house_password
    settings = Settings(house_code="TEST123", house_password=None)

    # Simulate the startup validation that happens in lifespan
    with pytest.raises(ValueError, match="House onboarding password credential not configured"):
        settings.require_credential("house_password", "House onboarding password")


def test_startup_fails_with_empty_house_code():
    """Test that application startup fails when house_code is empty string."""
    # Create settings with empty house_code
    settings = Settings(house_code="", house_password="test_password")

    # Simulate the startup validation that happens in lifespan
    with pytest.raises(ValueError, match="House onboarding code credential not configured"):
        settings.require_credential("house_code", "House onboarding code")


def test_startup_succeeds_with_valid_credentials():
    """Test that validation passes when both credentials are properly set."""
    # Create settings with valid credentials
    settings = Settings(house_code="TEST123", house_password="test_password")

    # Should not raise any exception
    house_code = settings.require_credential("house_code", "House onboarding code")
    house_password = settings.require_credential("house_password", "House onboarding password")

    assert house_code == "TEST123"
    assert house_password == "test_password"


@pytest.mark.asyncio
async def test_fastapi_lifespan_validates_credentials():
    """Test that FastAPI lifespan context manager validates credentials at startup."""
    from fastapi import FastAPI

    # Mock the settings to have missing credentials
    with patch("src.main.settings") as mock_settings:
        mock_settings.require_credential = Mock(
            side_effect=ValueError("House onboarding code credential not configured")
        )

        # Import the lifespan after patching
        from src.main import lifespan

        # Create a test app
        test_app = FastAPI()

        # The lifespan should raise ValueError when entering the context
        with pytest.raises(ValueError, match="House onboarding code credential not configured"):
            async with lifespan(test_app):
                pass  # Should never reach here
