"""Unit tests for verification_service module."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.db_client import RecordNotFoundError
from src.domain.chore import ChoreState
from src.services import chore_service, verification_service
from src.services.verification_service import VerificationDecision


@pytest.fixture
def patched_verification_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""

    # Patch all db_client functions
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)

    return in_memory_db


@pytest.mark.unit
class TestRequestVerification:
    """Tests for request_verification function."""

    @pytest.fixture
    async def todo_chore(self, patched_verification_db):
        """Create a chore in TODO state."""
        return await chore_service.create_chore(
            title="Test Chore",
            description="Test chore",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

    async def test_request_verification_success(self, patched_verification_db, todo_chore):
        """Test requesting verification for a chore."""
        log_record = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id="user1",
            notes="I finished this",
        )

        # Verify log was created
        assert log_record["chore_id"] == todo_chore["id"]
        assert log_record["user_id"] == "user1"
        assert "claimed_completion" in log_record["action"]
        assert "I finished this" in log_record["notes"]

        # Verify chore state changed
        updated_chore = await chore_service.get_chore_by_id(chore_id=todo_chore["id"])
        assert updated_chore["current_state"] == ChoreState.PENDING_VERIFICATION

    async def test_request_verification_without_notes(self, patched_verification_db, todo_chore):
        """Test requesting verification without notes."""
        log_record = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id="user1",
            notes="",
        )

        assert log_record["action"] == "claimed_completion"

    async def test_request_verification_chore_not_found(self, patched_verification_db):
        """Test requesting verification for non-existent chore raises error."""
        with pytest.raises(RecordNotFoundError):
            await verification_service.request_verification(
                chore_id="nonexistent_id",
                claimer_user_id="user1",
                notes="Test",
            )

    @patch("src.services.verification_service.notification_service")
    async def test_request_verification_sends_notifications(self, mock_notify, patched_verification_db, todo_chore):
        """Verify notification service is called when requesting verification."""
        mock_notify.send_verification_request = AsyncMock(return_value=[])

        result = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id="user1",
            notes="Done!",
        )

        mock_notify.send_verification_request.assert_called_once_with(
            log_id=result["id"],
            chore_id=todo_chore["id"],
            claimer_user_id="user1",
        )

    @patch("src.services.verification_service.notification_service")
    async def test_request_verification_succeeds_if_notification_fails(
        self, mock_notify, patched_verification_db, todo_chore
    ):
        """Claim should succeed even if notifications fail."""
        mock_notify.send_verification_request = AsyncMock(side_effect=Exception("Twilio error"))

        # Should not raise
        result = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id="user1",
        )

        assert result is not None
        assert result["action"] == "claimed_completion"


@pytest.mark.unit
class TestVerifyChore:
    """Tests for verify_chore function."""

    @pytest.fixture
    async def pending_chore_with_claim(self, patched_verification_db):
        """Create a chore with a verification claim."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Request verification (creates claim log)
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id="user1",
            notes="Completed",
        )

        return await chore_service.get_chore_by_id(chore_id=chore["id"])

    async def test_verify_chore_approve(self, patched_verification_db, pending_chore_with_claim):
        """Test approving a chore verification."""
        result = await verification_service.verify_chore(
            chore_id=pending_chore_with_claim["id"],
            verifier_user_id="user2",  # Different from claimer
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        assert result["id"] == pending_chore_with_claim["id"]
        assert result["current_state"] == ChoreState.COMPLETED

    async def test_verify_chore_reject(self, patched_verification_db, pending_chore_with_claim):
        """Test rejecting a chore verification."""
        result = await verification_service.verify_chore(
            chore_id=pending_chore_with_claim["id"],
            verifier_user_id="user2",
            decision=VerificationDecision.REJECT,
            reason="Not done properly",
        )

        assert result["id"] == pending_chore_with_claim["id"]
        assert result["current_state"] == ChoreState.CONFLICT

    async def test_verify_chore_self_verification_fails(self, patched_verification_db, pending_chore_with_claim):
        """Test that claimer cannot verify their own chore."""
        with pytest.raises(PermissionError, match="cannot verify their own chore claim"):
            await verification_service.verify_chore(
                chore_id=pending_chore_with_claim["id"],
                verifier_user_id="user1",  # Same as claimer
                decision=VerificationDecision.APPROVE,
                reason="",
            )

    async def test_verify_chore_no_claim_log_found(self, patched_verification_db):
        """Test verifying chore with no claim log raises error."""
        # Create a chore but don't claim it
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Manually transition to pending (bypassing normal claim flow)
        await chore_service.mark_pending_verification(chore_id=chore["id"])

        with pytest.raises(RecordNotFoundError, match="No claim log found"):
            await verification_service.verify_chore(
                chore_id=chore["id"],
                verifier_user_id="user2",
                decision=VerificationDecision.APPROVE,
                reason="",
            )


@pytest.mark.unit
class TestGetPendingVerifications:
    """Tests for get_pending_verifications function."""

    @pytest.fixture
    async def setup_pending_chores(self, patched_verification_db):
        """Create multiple chores with different states and claims."""
        # Chore 1: Pending verification claimed by user1
        chore1 = await chore_service.create_chore(
            title="Chore 1",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        await verification_service.request_verification(
            chore_id=chore1["id"],
            claimer_user_id="user1",
            notes="Done",
        )

        # Chore 2: Pending verification claimed by user2
        chore2 = await chore_service.create_chore(
            title="Chore 2",
            description="Test",
            recurrence="0 11 * * *",
            assigned_to="user2",
        )
        await verification_service.request_verification(
            chore_id=chore2["id"],
            claimer_user_id="user2",
            notes="Done",
        )

        # Chore 3: TODO state (not pending verification)
        chore3 = await chore_service.create_chore(
            title="Chore 3",
            description="Test",
            recurrence="0 12 * * *",
            assigned_to="user3",
        )

        return {"chore1": chore1, "chore2": chore2, "chore3": chore3}

    async def test_get_all_pending_verifications(self, patched_verification_db, setup_pending_chores):
        """Test getting all pending verifications without user filter."""
        result = await verification_service.get_pending_verifications()

        assert len(result) == 2
        assert all(chore["current_state"] == ChoreState.PENDING_VERIFICATION for chore in result)

    async def test_get_pending_verifications_excluding_user(self, patched_verification_db, setup_pending_chores):
        """Test getting pending verifications excluding those claimed by specific user."""
        # user1 should only see chores they didn't claim
        result = await verification_service.get_pending_verifications(user_id="user1")

        assert len(result) == 1
        # Should only contain chore2 (claimed by user2)
        assert result[0]["id"] == setup_pending_chores["chore2"]["id"]

    async def test_get_pending_verifications_user_claimed_all(self, patched_verification_db, setup_pending_chores):
        """Test user who claimed all pending chores sees none."""
        # Create scenario where user3 claimed both chores
        chore4 = await chore_service.create_chore(
            title="Chore 4",
            description="Test",
            recurrence="0 13 * * *",
            assigned_to="user3",
        )
        await verification_service.request_verification(
            chore_id=chore4["id"],
            claimer_user_id="user3",
            notes="Done",
        )

        # user3 should not see their own claim
        result = await verification_service.get_pending_verifications(user_id="user3")

        # Should not include chore4
        assert not any(chore["id"] == chore4["id"] for chore in result)

    async def test_get_pending_verifications_empty(self, patched_verification_db):
        """Test getting pending verifications when none exist."""
        result = await verification_service.get_pending_verifications()

        assert result == []


@pytest.mark.unit
class TestVerificationWorkflow:
    """Integration-style tests for the full verification workflow."""

    async def test_full_approval_workflow(self, patched_verification_db):
        """Test complete workflow: create -> claim -> approve."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Claim completion
        claim_log = await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id="user1",
            notes="All done!",
        )

        assert "claimed_completion" in claim_log["action"]

        # Verify chore state
        chore_after_claim = await chore_service.get_chore_by_id(chore_id=chore["id"])
        assert chore_after_claim["current_state"] == ChoreState.PENDING_VERIFICATION

        # Approve verification
        final_chore = await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id="user2",
            decision=VerificationDecision.APPROVE,
            reason="Verified!",
        )

        assert final_chore["current_state"] == ChoreState.COMPLETED

    async def test_full_rejection_workflow(self, patched_verification_db):
        """Test complete workflow: create -> claim -> reject."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Claim completion
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id="user1",
            notes="Done",
        )

        # Reject verification
        final_chore = await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id="user2",
            decision=VerificationDecision.REJECT,
            reason="Not acceptable",
        )

        assert final_chore["current_state"] == ChoreState.CONFLICT


@pytest.mark.unit
class TestVerificationCacheInvalidation:
    """Tests for cache invalidation during verification workflow."""

    @patch("src.services.verification_service.analytics_service.invalidate_leaderboard_cache")
    async def test_approve_verification_invalidates_cache(self, mock_invalidate_cache, patched_verification_db):
        """Verify cache is invalidated when chore verification is approved."""
        mock_invalidate_cache.return_value = None

        # Create and claim chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id="user1",
            notes="Done",
        )

        # Approve verification
        await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id="user2",
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        # Verify cache invalidation was called
        mock_invalidate_cache.assert_called_once()

    @patch("src.services.verification_service.analytics_service.invalidate_leaderboard_cache")
    async def test_reject_verification_invalidates_cache(self, mock_invalidate_cache, patched_verification_db):
        """Verify cache is invalidated when chore verification is rejected."""
        mock_invalidate_cache.return_value = None

        # Create and claim chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id="user1",
            notes="Done",
        )

        # Reject verification
        await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id="user2",
            decision=VerificationDecision.REJECT,
            reason="Not acceptable",
        )

        # Verify cache invalidation was called
        mock_invalidate_cache.assert_called_once()

    @patch("src.services.analytics_service.redis_client.keys")
    async def test_verification_succeeds_if_cache_invalidation_fails(self, mock_redis_keys, patched_verification_db):
        """Verify verification succeeds even if cache invalidation fails."""
        # Mock Redis to fail - this tests the internal exception handling in invalidate_leaderboard_cache
        mock_redis_keys.side_effect = Exception("Redis connection error")

        # Create and claim chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id="user1",
            notes="Done",
        )

        # Approve verification - should succeed despite cache failure
        result = await verification_service.verify_chore(
            chore_id=chore["id"],
            verifier_user_id="user2",
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        # Verify chore was still completed successfully
        assert result["current_state"] == ChoreState.COMPLETED

        # Verify Redis was accessed (cache invalidation was attempted)
        mock_redis_keys.assert_called_once()
