"""Pytest configuration and fixtures for unit tests."""

import asyncio
import contextlib

import pytest

from src.core.db_client import _db_connections
from src.interface.whatsapp_sender import SendMessageResult
from tests.unit.mocks import InMemoryDBClient


@pytest.fixture(autouse=True, scope="session")
def _close_leaked_db_connections():
    """Close any aiosqlite connections leaked during tests to prevent process hang."""
    yield
    for conn in list(_db_connections.values()):
        with contextlib.suppress(Exception):
            asyncio.get_event_loop().run_until_complete(conn.close())
    _db_connections.clear()


@pytest.fixture
def in_memory_db():
    """Provides a fresh InMemoryDBClient for each test."""
    return InMemoryDBClient()


async def _mock_send_text_message(**kwargs) -> SendMessageResult:
    """Mock WhatsApp sender that returns success instantly."""
    return SendMessageResult(success=True, message_id="mock_message_id")


async def _mock_invalidate_cache() -> None:
    """Mock cache invalidation that does nothing."""
    pass


@pytest.fixture
def patched_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient.

    Also patches external services (WhatsApp, analytics cache) to avoid
    real HTTP calls and retry delays in unit tests.
    """

    # Patch all db_client functions
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)

    # Patch WhatsApp sender to avoid real HTTP calls and retry delays
    monkeypatch.setattr(
        "src.interface.whatsapp_sender.send_text_message",
        _mock_send_text_message,
    )

    # Patch analytics service cache invalidation
    monkeypatch.setattr(
        "src.services.analytics_service.invalidate_leaderboard_cache",
        _mock_invalidate_cache,
    )

    return in_memory_db


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
