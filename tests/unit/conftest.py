"""Pytest configuration and fixtures for unit tests."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.core import config as config_module, db_client as db_module
from src.core.config import Settings
from src.interface.whatsapp_sender import SendMessageResult


class DatabaseClient:
    """Wrapper for db_client module to provide object-like interface for tests."""

    async def create_record(self, *, collection: str, data: dict) -> dict:
        return await db_module.create_record(collection=collection, data=data)

    async def get_record(self, *, collection: str, record_id: str) -> dict | None:
        return await db_module.get_record(collection=collection, record_id=record_id)

    async def update_record(self, *, collection: str, record_id: str, data: dict) -> dict:
        return await db_module.update_record(collection=collection, record_id=record_id, data=data)

    async def delete_record(self, *, collection: str, record_id: str) -> bool:
        await db_module.delete_record(collection=collection, record_id=record_id)
        return True

    async def list_records(self, *, collection: str, **kwargs) -> list[dict]:
        return await db_module.list_records(collection=collection, **kwargs)

    async def get_first_record(self, *, collection: str, filter_query: str) -> dict | None:
        return await db_module.get_first_record(collection=collection, filter_query=filter_query)


@pytest.fixture
def mock_db_module_for_unit_tests(test_settings: Settings) -> Iterator[None]:
    """Patch settings globally for all modules to use test configuration.

    This ensures all modules use the test settings (including test SQLite DB path)
    instead of production settings.

    Args:
        test_settings: Test Settings object

    Yields:
        None - Settings are patched globally
    """
    monkeypatch = pytest.MonkeyPatch()

    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(db_module, "settings", test_settings)

    yield

    monkeypatch.undo()


@pytest.fixture
def patched_settings_for_unit_tests(sqlite_db: Path) -> Settings:
    """Create test settings for unit tests.

    Args:
        sqlite_db: Path to test SQLite database

    Returns:
        Settings object configured for tests
    """
    return Settings(
        sqlite_db_path=str(sqlite_db),
        openrouter_api_key="test_key",
        waha_base_url="http://waha:3000",
        waha_webhook_secret="test_secret",
        admin_password="test_admin",
        secret_key="test_key",
        logfire_token="test_logfire",
        model_id="anthropic/claude-3.5-sonnet",
        is_production=False,
    )


class InMemoryDBPlaceholder:
    """Placeholder for tests outside the scope of US-009.

    Tests should be migrated to use db_client fixture with real SQLite.
    This class exists only to prevent import errors in other test files.
    """

    async def create_record(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Tests should use db_client fixture with real SQLite")

    async def get_record(self, collection: str, record_id: str) -> dict[str, Any]:
        raise NotImplementedError("Tests should use db_client fixture with real SQLite")

    async def update_record(self, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Tests should use db_client fixture with real SQLite")

    async def delete_record(self, collection: str, record_id: str) -> bool:
        raise NotImplementedError("Tests should use db_client fixture with real SQLite")

    async def list_records(
        self,
        collection: str,
        page: int = 1,
        per_page: int = 50,
        filter_query: str = "",
        sort: str = "",
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("Tests should use db_client fixture with real SQLite")

    async def get_first_record(self, collection: str, filter_query: str) -> dict[str, Any] | None:
        raise NotImplementedError("Tests should use db_client fixture with real SQLite")


@pytest.fixture
def in_memory_db():
    """Placeholder fixture for tests outside scope of US-009.

    Tests should be migrated to use db_client fixture with real SQLite.
    """
    return InMemoryDBPlaceholder()


async def _mock_send_text_message(**kwargs) -> SendMessageResult:
    """Mock WhatsApp sender that returns success instantly."""
    return SendMessageResult(success=True, message_id="mock_message_id", error=None)


async def _mock_invalidate_cache() -> None:
    """Mock cache invalidation that does nothing."""
    pass


@pytest.fixture
def patched_db(db_client, monkeypatch):
    """Patches external services (WhatsApp, analytics cache) for unit tests.

    Uses real SQLite database via db_client fixture from tests/conftest.py
    to avoid mocks while preventing real HTTP calls and retry delays.

    Note: Settings are patched by mock_db_module_for_unit_tests fixture.
    """
    monkeypatch.setattr(
        "src.modules.tasks.analytics.invalidate_leaderboard_cache",
        _mock_invalidate_cache,
    )


@pytest.fixture
def sample_user_data():
    """Returns sample user data for testing."""
    return {
        "username": "testuser",
        "phone": "+1234567890",
        "email": "test@example.com",
        "password": "securepass123",
        "passwordConfirm": "securepass123",
    }


@pytest.fixture
def sample_chore_data():
    """Returns sample chore data for testing."""
    return {
        "title": "Test Chore",
        "description": "A test chore",
        "assigned_to": [],
        "frequency": "daily",
        "points": 10,
    }
