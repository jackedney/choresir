"""Pytest configuration and fixtures for integration tests."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.retry_handler import reset_retry_handler


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
