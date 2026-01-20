"""Security tests for personal_verification_service module."""

import pytest
from src.services import personal_verification_service
from tests.unit.mocks import InMemoryDBClient
from datetime import datetime

@pytest.fixture
def in_memory_db():
    return InMemoryDBClient()

@pytest.fixture
def patched_db(monkeypatch, in_memory_db):
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)
    return in_memory_db

@pytest.mark.unit
async def test_get_personal_stats_injection_prevented(patched_db):
    """Test that get_personal_stats is secure against filter injection."""

    # Setup data directly in DB: A verified log for 'victim'
    await patched_db.create_record("personal_chore_logs", {
        "owner_phone": "victim",
        "verification_status": "VERIFIED",
        "completed_at": datetime.now().isoformat(),
        "personal_chore_id": "chore1"
    })

    # Attempt injection: We want logs for 'attacker' OR 'victim'
    injection_payload = 'attacker" || owner_phone="victim'

    # Execute service method with injected payload
    # get_personal_chores will be called first with this payload, but it is sanitized there too.
    stats = await personal_verification_service.get_personal_stats(
        owner_phone=injection_payload
    )

    # If vulnerable, the injection would cause the query to match 'victim's records
    # If secure, it searches for a literal string and finds nothing
    assert stats.completions_this_period == 0, "SQL Injection successful! Victim logs leaked."
