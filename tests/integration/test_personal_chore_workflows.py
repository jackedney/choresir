"""Integration tests for personal chore workflows."""

from datetime import datetime, timedelta

import pytest

from src.services import (
    personal_chore_service,
    personal_verification_service,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_self_verified_personal_chore_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Create self-verified personal chore → log completion → verify auto-completion."""
    # Step 1: Alice creates a self-verified personal chore
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Meditate",
        recurrence="every morning",
        accountability_partner_phone=None,
    )

    assert chore["title"] == "Meditate"
    assert chore["owner_phone"] == sample_users["alice"]["phone"]
    assert chore["accountability_partner_phone"] == ""
    assert chore["status"] == "ACTIVE"

    # Step 2: Alice logs completion
    log = await personal_verification_service.log_personal_chore(
        chore_id=chore["id"],
        owner_phone=sample_users["alice"]["phone"],
        notes="Morning meditation",
    )

    assert log.verification_status == "SELF_VERIFIED"
    assert log.owner_phone == sample_users["alice"]["phone"]
    assert log.accountability_partner_phone == ""

    # Step 3: Verify stats
    stats = await personal_verification_service.get_personal_stats(
        owner_phone=sample_users["alice"]["phone"],
        period_days=7,
    )

    assert stats.total_chores == 1
    assert stats.completions_this_period == 1
    assert stats.pending_verifications == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accountability_partner_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Create chore with partner → log → partner approves → verify completion."""
    # Step 1: Alice creates personal chore with Bob as accountability partner
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Gym",
        recurrence="every 2 days",
        accountability_partner_phone=sample_users["bob"]["phone"],
    )

    assert chore["accountability_partner_phone"] == sample_users["bob"]["phone"]

    # Step 2: Alice logs completion
    log = await personal_verification_service.log_personal_chore(
        chore_id=chore["id"],
        owner_phone=sample_users["alice"]["phone"],
        notes="Leg day",
    )

    assert log.verification_status == "PENDING"
    assert log.accountability_partner_phone == sample_users["bob"]["phone"]

    # Step 3: Bob can see pending verifications
    pending = await personal_verification_service.get_pending_partner_verifications(
        partner_phone=sample_users["bob"]["phone"],
    )

    assert len(pending) == 1
    assert pending[0].id == log.id
    assert pending[0].chore_title == "Gym"

    # Step 4: Bob approves
    updated_log = await personal_verification_service.verify_personal_chore(
        log_id=log.id,
        verifier_phone=sample_users["bob"]["phone"],
        approved=True,
        feedback="Saw you there!",
    )

    assert updated_log.verification_status == "VERIFIED"
    assert updated_log.partner_feedback == "Saw you there!"

    # Step 5: Verify stats updated
    stats = await personal_verification_service.get_personal_stats(
        owner_phone=sample_users["alice"]["phone"],
        period_days=7,
    )

    assert stats.completions_this_period == 1
    assert stats.pending_verifications == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accountability_partner_rejection(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Partner rejects completion → verify status is REJECTED."""
    # Step 1: Create chore with partner
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Running",
        recurrence="every 3 days",
        accountability_partner_phone=sample_users["charlie"]["phone"],
    )

    # Step 2: Alice logs completion
    log = await personal_verification_service.log_personal_chore(
        chore_id=chore["id"],
        owner_phone=sample_users["alice"]["phone"],
    )

    # Step 3: Charlie rejects
    updated_log = await personal_verification_service.verify_personal_chore(
        log_id=log.id,
        verifier_phone=sample_users["charlie"]["phone"],
        approved=False,
        feedback="Didn't see you at the track",
    )

    assert updated_log.verification_status == "REJECTED"
    assert updated_log.partner_feedback == "Didn't see you at the track"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auto_verify_after_48_hours(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Log pending > 48h → auto-verify job → verify status changes."""
    # Step 1: Create chore with partner
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Yoga",
        recurrence="every morning",
        accountability_partner_phone=sample_users["bob"]["phone"],
    )

    # Step 2: Create log with old timestamp (simulate 48+ hours ago)
    old_timestamp = (datetime.now() - timedelta(hours=49)).isoformat()
    log_data = {
        "personal_chore_id": chore["id"],
        "owner_phone": sample_users["alice"]["phone"],
        "completed_at": old_timestamp,
        "verification_status": "PENDING",
        "accountability_partner_phone": sample_users["bob"]["phone"],
        "partner_feedback": "",
        "notes": "",
    }
    log = await db_client.create_record(collection="personal_chore_logs", data=log_data)

    assert log["verification_status"] == "PENDING"

    # Step 3: Run auto-verify job
    count = await personal_verification_service.auto_verify_expired_logs()

    assert count == 1

    # Step 4: Verify log is now VERIFIED
    updated_log = await db_client.get_record(
        collection="personal_chore_logs",
        record_id=log["id"],
    )

    assert updated_log["verification_status"] == "VERIFIED"
    assert "48 hours" in updated_log["partner_feedback"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_privacy_isolation(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Alice's personal chores are not visible to Bob."""
    # Step 1: Alice creates personal chore
    alice_chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Alice's Secret Project",
        recurrence="every 7 days",
    )

    # Step 2: Bob creates personal chore
    bob_chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["bob"]["phone"],
        title="Bob's Personal Task",
        recurrence="every 5 days",
    )

    # Step 3: Alice can only see her chores
    alice_chores = await personal_chore_service.get_personal_chores(
        owner_phone=sample_users["alice"]["phone"],
    )

    assert len(alice_chores) == 1
    assert alice_chores[0]["id"] == alice_chore["id"]
    assert alice_chores[0]["title"] == "Alice's Secret Project"

    # Step 4: Bob can only see his chores
    bob_chores = await personal_chore_service.get_personal_chores(
        owner_phone=sample_users["bob"]["phone"],
    )

    assert len(bob_chores) == 1
    assert bob_chores[0]["id"] == bob_chore["id"]
    assert bob_chores[0]["title"] == "Bob's Personal Task"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_partner_leaving_household(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Partner leaves household → log auto-converts to self-verified."""
    # Step 1: Alice creates chore with Bob as partner
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Study",
        recurrence="every 2 days",
        accountability_partner_phone=sample_users["bob"]["phone"],
    )

    # Step 2: Bob leaves household (delete user)
    await db_client.delete_record(
        collection="users",
        record_id=sample_users["bob"]["id"],
    )

    # Step 3: Alice logs completion
    log = await personal_verification_service.log_personal_chore(
        chore_id=chore["id"],
        owner_phone=sample_users["alice"]["phone"],
    )

    # Should auto-convert to SELF_VERIFIED since Bob is no longer active
    assert log.verification_status == "SELF_VERIFIED"
    assert log.accountability_partner_phone == ""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fuzzy_matching(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Fuzzy matching works for personal chore titles."""
    # Step 1: Create chore with full title
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Go to the gym",
        recurrence="every 2 days",
    )

    # Step 2: Get all chores
    chores = await personal_chore_service.get_personal_chores(
        owner_phone=sample_users["alice"]["phone"],
    )

    # Test exact match
    match = personal_chore_service.fuzzy_match_personal_chore(chores, "Go to the gym")
    assert match is not None
    assert match["id"] == chore["id"]

    # Test contains match
    match = personal_chore_service.fuzzy_match_personal_chore(chores, "gym")
    assert match is not None
    assert match["id"] == chore["id"]

    # Test partial word match
    match = personal_chore_service.fuzzy_match_personal_chore(chores, "go")
    assert match is not None
    assert match["id"] == chore["id"]

    # Test no match
    match = personal_chore_service.fuzzy_match_personal_chore(chores, "running")
    assert match is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wrong_partner_cannot_verify(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Only designated accountability partner can verify."""
    # Step 1: Alice creates chore with Bob as partner
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Coding practice",
        recurrence="every morning",
        accountability_partner_phone=sample_users["bob"]["phone"],
    )

    # Step 2: Alice logs completion
    log = await personal_verification_service.log_personal_chore(
        chore_id=chore["id"],
        owner_phone=sample_users["alice"]["phone"],
    )

    # Step 3: Charlie tries to verify (should fail)
    with pytest.raises(PermissionError, match="Only accountability partner"):
        await personal_verification_service.verify_personal_chore(
            log_id=log.id,
            verifier_phone=sample_users["charlie"]["phone"],
            approved=True,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_personal_chore(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Soft delete (archive) personal chore."""
    # Step 1: Create chore
    chore = await personal_chore_service.create_personal_chore(
        owner_phone=sample_users["alice"]["phone"],
        title="Temporary task",
        recurrence="every 7 days",
    )

    # Step 2: Delete (archive) chore
    await personal_chore_service.delete_personal_chore(
        chore_id=chore["id"],
        owner_phone=sample_users["alice"]["phone"],
    )

    # Step 3: Verify chore no longer in active list
    active_chores = await personal_chore_service.get_personal_chores(
        owner_phone=sample_users["alice"]["phone"],
        status="ACTIVE",
    )

    assert len(active_chores) == 0

    # Step 4: Verify chore is archived
    archived_chores = await personal_chore_service.get_personal_chores(
        owner_phone=sample_users["alice"]["phone"],
        status="ARCHIVED",
    )

    assert len(archived_chores) == 1
    assert archived_chores[0]["id"] == chore["id"]
