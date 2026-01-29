"""Security tests for user onboarding."""

import pytest
from src.core.config import settings
from src.services import user_service
from tests.unit.mocks import InMemoryDBClient


@pytest.fixture
def in_memory_db():
    """Provides a fresh InMemoryDBClient."""
    return InMemoryDBClient()


@pytest.fixture
def patched_user_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""
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
async def test_auto_provisioned_passwords_are_random(
    patched_user_db, patched_settings, valid_join_credentials
):
    """Test that auto-provisioned user passwords are random and secure."""
    # Create first user
    user1_req = {
        "phone": "+1234567890",
        "name": "User One",
        "house_code": valid_join_credentials["house_code"],
        "password": valid_join_credentials["house_password"],
    }
    user1 = await user_service.request_join(**user1_req)

    # Create second user
    user2_req = {
        "phone": "+1987654321",
        "name": "User Two",
        "house_code": valid_join_credentials["house_code"],
        "password": valid_join_credentials["house_password"],
    }
    user2 = await user_service.request_join(**user2_req)

    # Retrieve the full records from DB to check passwords
    # Note: request_join returns the created record, but let's be sure.
    # In real PocketBase, password is not returned in responses usually, but InMemoryDBClient
    # returns exactly what was stored.

    pass1 = user1.get("password")
    pass2 = user2.get("password")

    # Vulnerability check: Password should NOT be the hardcoded string
    assert pass1 != "temp_password_will_be_set_on_activation", "Password is hardcoded!"

    # Uniqueness check: Passwords should be different for different users
    assert pass1 != pass2, "Passwords are not unique per user!"

    # Strength check: Password should be reasonably long
    assert len(pass1) >= 16, "Password is too short!"
