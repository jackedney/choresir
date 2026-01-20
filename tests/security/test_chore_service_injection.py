"""Security tests for chore_service module."""

import pytest
from src.services import chore_service
from tests.unit.mocks import InMemoryDBClient

@pytest.fixture
def in_memory_db():
    """Fixture to provide InMemoryDBClient instance."""
    return InMemoryDBClient()

@pytest.fixture
def patched_chore_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)
    return in_memory_db

@pytest.mark.unit
async def test_get_chores_sql_injection_prevented(patched_chore_db):
    """Test that get_chores is secure against filter injection."""

    # Create a chore assigned to 'victim'
    await chore_service.create_chore(
        title="Victim Chore",
        description="Secret",
        recurrence="0 10 * * *",
        assigned_to="victim"
    )

    # Create a chore assigned to 'attacker'
    await chore_service.create_chore(
        title="Attacker Chore",
        description="Public",
        recurrence="0 10 * * *",
        assigned_to="attacker"
    )

    # Attempt injection: We want chores for 'attacker' OR 'victim'
    # The filter constructed is: assigned_to = "{user_id}"
    # We want: assigned_to = "attacker" || assigned_to = "victim"
    # So we inject: attacker" || assigned_to = "victim

    injection_payload = 'attacker" || assigned_to = "victim'

    # Verify that sanitization prevents the injection
    chores = await chore_service.get_chores(user_id=injection_payload)

    titles = [c['title'] for c in chores]

    # We expect NO chores because "attacker\" || assigned_to = \"victim" is not a valid user ID
    # and certainly matches neither "victim" nor "attacker" literally.
    assert "Victim Chore" not in titles, "SQL Injection successful! Victim chore leaked."
    assert "Attacker Chore" not in titles, "Sanitization should have prevented matching 'attacker' too."
