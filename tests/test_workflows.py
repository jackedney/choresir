"""Integration tests for core workflows."""

import pytest

from src.domain.chore import ChoreState
from src.services import chore_service, conflict_service, user_service, verification_service
from tests.conftest import create_test_admin


@pytest.mark.asyncio
async def test_join_house_workflow(mock_db_module, db_client) -> None:
    """Test: Join House workflow (request → approve → active)."""
    # Step 1: User requests to join
    user = await user_service.request_join(
        phone="+15550001111",
        name="Diana Newbie",
        house_code="TEST123",
        password="testpass",
    )

    assert user["phone"] == "+15550001111"
    assert user["name"] == "Diana Newbie"
    assert user["status"] == "pending"
    assert user["role"] == "member"

    # Step 2: Create admin to approve
    admin = await create_test_admin(
        phone="+15550000000",
        name="Admin User",
        db_client=db_client,
    )

    # Step 3: Admin approves member
    approved_user = await user_service.approve_member(
        admin_user_id=admin["id"],
        target_phone="+15550001111",
    )

    assert approved_user["status"] == "active"

    # Verify user can be retrieved
    retrieved_user = await db_client.get_first_record(
        collection="users",
        filter_query='phone = "+15550001111"',
    )
    assert retrieved_user is not None
    assert retrieved_user["status"] == "active"


@pytest.mark.asyncio
async def test_create_and_complete_chore_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Create & Complete Chore workflow (create → log → verify → completed)."""
    # Step 1: Create chore
    chore = await chore_service.create_chore(
        title="Clean Bathroom",
        description="Scrub toilet, sink, and shower",
        recurrence="every 3 days",
        assigned_to=sample_users["bob"]["phone"],
    )

    assert chore["title"] == "Clean Bathroom"
    assert chore["assigned_to"] == sample_users["bob"]["id"]
    assert chore["current_state"] == ChoreState.TODO.value

    # Step 2: Bob logs completion
    from src.services.verification_service import VerificationDecision

    log = await verification_service.request_verification(
        chore_id=chore["id"],
        claimer_user_id=sample_users["bob"]["id"],
        notes="All clean!",
    )

    assert log["chore_id"] == chore["id"]
    assert log["user_id"] == sample_users["bob"]["id"]

    # Verify chore state changed
    updated_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert updated_chore["current_state"] == ChoreState.PENDING_VERIFICATION.value

    # Step 3: Alice verifies completion
    result = await verification_service.verify_chore(
        chore_id=chore["id"],
        verifier_user_id=sample_users["alice"]["id"],
        decision=VerificationDecision.APPROVE,
        reason="Looks good",
    )

    assert result["status"] == "approved"

    # Verify chore is completed
    final_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert final_chore["current_state"] == ChoreState.COMPLETED.value


@pytest.mark.asyncio
async def test_conflict_resolution_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Conflict Resolution workflow (log → reject → vote → resolve)."""
    # Step 1: Create chore
    chore = await chore_service.create_chore(
        title="Mow Lawn",
        description="Cut grass in front and back yard",
        recurrence="every 7 days",
        assigned_to=sample_users["charlie"]["phone"],
    )

    # Step 2: Charlie logs completion
    from src.services.verification_service import VerificationDecision

    await verification_service.request_verification(
        chore_id=chore["id"],
        claimer_user_id=sample_users["charlie"]["id"],
        notes="Lawn mowed",
    )

    # Step 3: Alice rejects the claim
    result = await verification_service.verify_chore(
        chore_id=chore["id"],
        verifier_user_id=sample_users["alice"]["id"],
        decision=VerificationDecision.REJECT,
        reason="Grass still too long",
    )

    assert result["status"] == "conflict"

    # Verify chore moved to CONFLICT state
    conflict_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert conflict_chore["current_state"] == ChoreState.CONFLICT.value

    # Step 4: Bob votes (only eligible voter)
    from src.services.conflict_service import VoteChoice

    vote = await conflict_service.cast_vote(
        chore_id=chore["id"],
        voter_user_id=sample_users["bob"]["id"],
        choice=VoteChoice.YES,
    )

    assert vote["action"] == "vote_yes"

    # Step 5: Tally votes (should resolve conflict)
    from src.services.conflict_service import VoteResult

    tally_result, updated_chore = await conflict_service.tally_votes(chore_id=chore["id"])

    assert tally_result == VoteResult.APPROVED

    # Verify chore is completed
    final_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert final_chore["current_state"] == ChoreState.COMPLETED.value


@pytest.mark.asyncio
async def test_robin_hood_swap_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Robin Hood Swap workflow (User A logs User B's chore)."""
    # Step 1: Create chore assigned to Bob
    chore = await chore_service.create_chore(
        title="Vacuum Living Room",
        description="Vacuum carpet and under furniture",
        recurrence="every 5 days",
        assigned_to=sample_users["bob"]["phone"],
    )

    assert chore["assigned_to"] == sample_users["bob"]["id"]

    # Step 2: Alice logs completion on Bob's behalf
    from src.services.verification_service import VerificationDecision

    log = await verification_service.request_verification(
        chore_id=chore["id"],
        claimer_user_id=sample_users["alice"]["id"],
        notes="Helped Bob out (swap)",
    )

    assert log["user_id"] == sample_users["alice"]["id"]
    # Note: is_swap functionality may need to be tracked in notes or separate field

    # Step 3: Charlie verifies
    result = await verification_service.verify_chore(
        chore_id=chore["id"],
        verifier_user_id=sample_users["charlie"]["id"],
        decision=VerificationDecision.APPROVE,
        reason="Confirmed clean",
    )

    assert result["status"] == "approved"

    # Verify chore is completed
    final_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert final_chore["current_state"] == ChoreState.COMPLETED.value


@pytest.mark.asyncio
async def test_invalid_house_credentials(mock_db_module, db_client) -> None:
    """Test: Reject join request with invalid credentials."""
    with pytest.raises(ValueError, match="Invalid house code or password"):
        await user_service.request_join(
            phone="+15550009999",
            name="Evil User",
            house_code="WRONG",
            password="wrongpass",
        )


@pytest.mark.asyncio
async def test_verifier_cannot_be_claimer(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Verifier cannot be the same as claimer."""
    from src.services.verification_service import VerificationDecision

    chore = await chore_service.create_chore(
        title="Water Plants",
        description="Water all indoor plants",
        recurrence="every 2 days",
        assigned_to=sample_users["bob"]["phone"],
    )

    await verification_service.request_verification(
        chore_id=chore["id"],
        claimer_user_id=sample_users["bob"]["id"],
        notes="Plants watered",
    )

    # Bob tries to verify his own claim
    with pytest.raises(PermissionError, match="Verifier cannot be the claimer"):
        await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id=sample_users["bob"]["id"],
            decision=VerificationDecision.APPROVE,
            reason="Self-verify",
        )
