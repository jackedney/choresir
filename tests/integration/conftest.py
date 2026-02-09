"""Pytest configuration and fixtures for integration tests."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.retry_handler import reset_retry_handler
from src.core import admin_notifier as admin_notifier_module, config as config_module, db_client as db_module
from src.services import house_config_service as house_config_service_module


logger = logging.getLogger(__name__)


@pytest.fixture
def mock_db_module(test_settings):
    """Patch settings globally for all modules to use test configuration.

    This ensures all modules use the test settings (including test SQLite DB path)
    instead of the production settings.

    Args:
        test_settings: Test Settings object from root conftest

    Yields:
        None - Settings are patched globally
    """
    # Patch the global settings in all modules that import it
    monkeypatch = pytest.MonkeyPatch()

    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(db_module, "settings", test_settings)
    monkeypatch.setattr(admin_notifier_module, "settings", test_settings)
    monkeypatch.setattr(house_config_service_module, "settings", test_settings)

    yield

    monkeypatch.undo()


@pytest.fixture(autouse=True)
def reset_agent_retry_handler():
    """Reset the global retry handler before each test to ensure clean state."""
    reset_retry_handler()
    yield
    # Clean up after test as well
    reset_retry_handler()


@pytest.fixture(autouse=True)
def mock_retry_handler_sleep():
    """Mock asyncio.sleep in retry handler to avoid actual delays in integration tests.

    The retry handler uses asyncio.sleep for exponential backoff between retries.
    In tests, we want to verify the retry behavior without waiting for actual delays.
    """
    with patch("src.agents.retry_handler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep
