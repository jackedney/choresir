"""Pytest configuration and fixtures for unit tests."""

import pytest

from tests.unit.mocks import InMemoryDBClient


@pytest.fixture
def in_memory_db():
    """Provides a fresh InMemoryDBClient for each test."""
    return InMemoryDBClient()


@pytest.fixture
def patched_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""

    # Patch all db_client functions
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)

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
