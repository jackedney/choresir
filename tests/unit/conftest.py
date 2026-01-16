"""Pytest configuration and fixtures for unit tests."""

import pytest

from tests.unit.mocks import InMemoryDBClient


@pytest.fixture
def in_memory_db():
    """Provides a fresh InMemoryDBClient for each test."""
    return InMemoryDBClient()


@pytest.fixture
def patched_db(monkeypatch, in_memory_db):
    """Patches src.core.database.get_db_client to return InMemoryDBClient."""

    def mock_get_db():
        return in_memory_db

    monkeypatch.setattr("src.core.database.get_db_client", mock_get_db)
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
