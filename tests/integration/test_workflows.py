"""Integration tests for core workflows."""

import pytest

from src.domain.chore import ChoreState
from src.domain.user import UserStatus
from src.services import chore_service, conflict_service, user_service, verification_service
from src.services.conflict_service import VoteChoice, VoteResult
from src.services.verification_service import VerificationDecision


@pytest.mark.integration
@pytest.mark.asyncio
async def test_new_user_registration_workflow(mock_db_module, db_client) -> None:
    """Test: New user registration via group (pending_name → provide name → active)."""
    # Step 1: Create pending_name user (simulates first message in group)
    user = await user_service.create_pending_name_user(phone="+15550001111")

    assert user["phone"] == "+15550001111"
    assert user["name"] == "Pending"
    assert user["status"] == UserStatus.PENDING_NAME
    assert user["role"] == "member"

    # Step 2: User provides their name
    updated_user = await user_service.update_user_name(
        user_id=user["id"],
        name="Diana Newbie",
    )

    assert updated_user["name"] == "Diana Newbie"

    # Step 3: Update status to active
    active_user = await user_service.update_user_status(
        user_id=user["id"],
        status=UserStatus.ACTIVE,
    )

    assert active_user["status"] == UserStatus.ACTIVE

    # Verify user can be retrieved
    retrieved_user = await db_client.get_first_record(
        collection="members",
        filter_query='phone = "+15550001111"',
    )
    assert retrieved_user is not None
    assert retrieved_user["status"] == UserStatus.ACTIVE
    assert retrieved_user["name"] == "Diana Newbie"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_complete_chore_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Create & Complete Chore workflow (create → log → verify → completed)."""
    # Step 1: Create chore
    chore = await chore_service.create_chore(
        title="Clean Bathroom",
        description="Scrub toilet, sink, and shower",
        recurrence="every 3 days",
        assigned_to=sample_users["bob"]["id"],
    )

    assert chore["title"] == "Clean Bathroom"
    assert chore["assigned_to"] == sample_users["bob"]["id"]
    assert chore["current_state"] == ChoreState.TODO.value

    # Step 2: Bob logs completion
    workflow = await verification_service.request_verification(
        chore_id=chore["id"],
        claimer_user_id=sample_users["bob"]["id"],
        notes="All clean!",
    )

    assert workflow["target_id"] == chore["id"]
    assert workflow["requester_user_id"] == sample_users["bob"]["id"]

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

    # verify_chore returns the updated chore record
    assert result["current_state"] == ChoreState.COMPLETED.value

    # Verify chore is completed
    final_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert final_chore["current_state"] == ChoreState.COMPLETED.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conflict_resolution_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Conflict Resolution workflow (log → reject → vote → resolve)."""
    # Step 1: Create chore
    chore = await chore_service.create_chore(
        title="Mow Lawn",
        description="Cut grass in front and back yard",
        recurrence="every 7 days",
        assigned_to=sample_users["charlie"]["id"],
    )

    # Step 2: Charlie logs completion
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

    # verify_chore returns the updated chore record
    assert result["current_state"] == ChoreState.CONFLICT.value

    # Verify chore moved to CONFLICT state
    conflict_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert conflict_chore["current_state"] == ChoreState.CONFLICT.value

    # Step 4: Bob votes (only eligible voter)
    vote = await conflict_service.cast_vote(
        chore_id=chore["id"],
        voter_user_id=sample_users["bob"]["id"],
        choice=VoteChoice.YES,
    )

    assert vote["action"] == "vote_yes"

    # Step 5: Tally votes (should resolve conflict)
    tally_result, _updated_chore = await conflict_service.tally_votes(chore_id=chore["id"])

    assert tally_result == VoteResult.APPROVED

    # Verify chore is completed
    final_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert final_chore["current_state"] == ChoreState.COMPLETED.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_robin_hood_swap_workflow(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Robin Hood Swap workflow (User A logs User B's chore)."""
    # Step 1: Create chore assigned to Bob
    chore = await chore_service.create_chore(
        title="Vacuum Living Room",
        description="Vacuum carpet and under furniture",
        recurrence="every 5 days",
        assigned_to=sample_users["bob"]["id"],
    )

    assert chore["assigned_to"] == sample_users["bob"]["id"]

    # Step 2: Alice logs completion on Bob's behalf
    workflow = await verification_service.request_verification(
        chore_id=chore["id"],
        claimer_user_id=sample_users["alice"]["id"],
        notes="Helped Bob out (swap)",
    )

    assert workflow["requester_user_id"] == sample_users["alice"]["id"]
    # Note: is_swap functionality is tracked in workflow metadata

    # Step 3: Charlie verifies
    result = await verification_service.verify_chore(
        chore_id=chore["id"],
        verifier_user_id=sample_users["charlie"]["id"],
        decision=VerificationDecision.APPROVE,
        reason="Confirmed clean",
    )

    # verify_chore returns the updated chore record
    assert result["current_state"] == ChoreState.COMPLETED.value

    # Verify chore is completed
    final_chore = await db_client.get_record(collection="chores", record_id=chore["id"])
    assert final_chore["current_state"] == ChoreState.COMPLETED.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verifier_cannot_be_claimer(mock_db_module, db_client, sample_users: dict) -> None:
    """Test: Verifier cannot be the same as claimer."""
    chore = await chore_service.create_chore(
        title="Water Plants",
        description="Water all indoor plants",
        recurrence="every 2 days",
        assigned_to=sample_users["bob"]["id"],
    )

    await verification_service.request_verification(
        chore_id=chore["id"],
        claimer_user_id=sample_users["bob"]["id"],
        notes="Plants watered",
    )

    # Bob tries to verify his own claim
    with pytest.raises(PermissionError, match="cannot verify their own chore claim"):
        await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id=sample_users["bob"]["id"],
            decision=VerificationDecision.APPROVE,
            reason="Self-verify",
        )
