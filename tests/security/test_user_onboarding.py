"""Security tests for user onboarding process."""

import pytest
import secrets
from src.core.config import settings
from src.services import user_service
from tests.unit.mocks import InMemoryDBClient
from src.domain.user import UserRole, UserStatus

@pytest.fixture
def patched_user_db(monkeypatch):
    """Patches src.core.db_client functions to use InMemoryDBClient."""
    in_memory_db = InMemoryDBClient()

    # Patch all db_client functions
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)

    return in_memory_db

@pytest.fixture
def valid_join_credentials():
    """Valid house code and password for testing."""
    return {
        "house_code": "HOUSE123",
        "house_password": "secret123",
    }

@pytest.fixture
def patched_settings(monkeypatch, valid_join_credentials):
    """Patch settings with test house credentials."""
    monkeypatch.setattr(settings, "house_code", valid_join_credentials["house_code"])
    monkeypatch.setattr(settings, "house_password", valid_join_credentials["house_password"])
    return settings

@pytest.mark.asyncio
async def test_request_join_generates_random_password(patched_user_db, patched_settings, valid_join_credentials):
    """Test that requesting to join generates a random, secure password."""

    # Request 1
    join_request_1 = {
        "phone": "+1234567890",
        "name": "User One",
        "house_code": valid_join_credentials["house_code"],
        "password": valid_join_credentials["house_password"],
    }

    user1 = await user_service.request_join(**join_request_1)

    # Assertions for User 1
    password_1 = user1["password"]
    assert password_1 != "temp_password_will_be_set_on_activation", "Password should not be the hardcoded default"
    assert len(password_1) >= 32, "Password should be at least 32 characters long"
    assert user1["passwordConfirm"] == password_1, "passwordConfirm must match password"

    # Request 2 (Different User)
    join_request_2 = {
        "phone": "+1987654321",
        "name": "User Two",
        "house_code": valid_join_credentials["house_code"],
        "password": valid_join_credentials["house_password"],
    }

    user2 = await user_service.request_join(**join_request_2)

    # Assertions for User 2
    password_2 = user2["password"]
    assert password_2 != "temp_password_will_be_set_on_activation"
    assert password_2 != password_1, "Passwords should be unique between users"
    assert len(password_2) >= 32
