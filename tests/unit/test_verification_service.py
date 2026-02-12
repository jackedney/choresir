"""Unit tests for verification_service module."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import src.modules.tasks.service as chore_service
import src.modules.tasks.verification as verification_service
from src.core import db_client as db_client_module
from src.core.db_client import create_record
from src.domain.create_models import UserCreate
from src.domain.task import TaskState
from src.domain.user import UserRole, UserStatus
from src.modules.tasks.verification import VerificationDecision
from tests.unit.conftest import DatabaseClient


@pytest.fixture
def patched_verification_db(mock_db_module_for_unit_tests: Any, db_client: DatabaseClient) -> DatabaseClient:
    """Patches settings and database for verification service tests.

    Uses real SQLite database via db_client fixture from tests/conftest.py.
    Settings are patched by mock_db_module_for_unit_tests fixture.
    """
    return DatabaseClient()


@pytest.fixture
async def setup_test_users(patched_verification_db: DatabaseClient) -> dict[str, dict[str, Any]]:
    """Create test users for workflow name resolution."""
    users = {}
    for i in range(1, 4):
        user_create = UserCreate(
            phone=f"+141555555{i}",
            name=f"User{i}",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        user = await create_record(collection="members", data=user_create.model_dump())
        users[f"user{i}"] = user
    return users


@pytest.mark.unit
class TestRequestVerification:
    """Tests for request_verification function."""

    @pytest.fixture
    async def todo_chore(
        self, patched_verification_db: DatabaseClient, setup_test_users: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Create a chore in TODO state."""
        user1_id = setup_test_users["user1"]["id"]
        return await chore_service.create_chore(
            title="Test Chore",
            description="Test chore",
            recurrence="0 10 * * *",
            assigned_to=str(user1_id),
        )

    async def test_request_verification_success(self, patched_verification_db, todo_chore, setup_test_users):
        """Test requesting verification for a chore."""
        user1_id = str(setup_test_users["user1"]["id"])
        workflow = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id=user1_id,
            notes="I finished this",
        )

        # Verify workflow was created
        assert workflow["target_id"] == todo_chore["id"]
        assert workflow["requester_user_id"] == user1_id
        assert workflow["type"] == "task_verification"
        assert workflow["metadata"]["notes"] == "I finished this"
        assert workflow["status"] == "pending"

        # Verify log entry was still created (audit trail)
        logs = await patched_verification_db.list_records(
            collection="task_logs",
            filter_query=f'task_id = "{todo_chore["id"]}" && action = "claimed_completion"',
        )
        assert len(logs) >= 1
        assert logs[0]["user_id"] == user1_id

        # Verify chore state changed
        updated_chore = await chore_service.get_chore_by_id(chore_id=todo_chore["id"])
        assert updated_chore["current_state"] == TaskState.PENDING_VERIFICATION

    async def test_request_verification_without_notes(self, patched_verification_db, todo_chore, setup_test_users):
        """Test requesting verification without notes."""
        workflow = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="",
        )

        assert workflow["type"] == "task_verification"
        assert workflow["metadata"]["notes"] == ""

    async def test_request_verification_chore_not_found(self, patched_verification_db, setup_test_users):
        """Test requesting verification for non-existent chore raises error."""
        with pytest.raises(KeyError):
            await verification_service.request_verification(
                chore_id="99999",
                claimer_user_id=str(setup_test_users["user1"]["id"]),
                notes="Test",
            )

    @patch("src.services.notification_service")
    async def test_request_verification_sends_notifications(
        self, mock_notify, patched_verification_db, todo_chore, setup_test_users
    ):
        """Verify notification service is called when requesting verification."""
        mock_notify.send_verification_request = AsyncMock(return_value=[])

        await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Done!",
        )

        # Get the log entry to verify notification was called with log_id
        logs = await patched_verification_db.list_records(
            collection="task_logs",
            filter_query=f'task_id = "{todo_chore["id"]}" && action = "claimed_completion"',
        )

        mock_notify.send_verification_request.assert_called_once_with(
            log_id=logs[0]["id"],
            task_id=todo_chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
        )

    @patch("src.services.notification_service")
    async def test_request_verification_succeeds_if_notification_fails(
        self, mock_notify, patched_verification_db, todo_chore, setup_test_users
    ):
        """Claim should succeed even if notifications fail."""
        mock_notify.send_verification_request = AsyncMock(side_effect=Exception("Twilio error"))

        # Should not raise
        result = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
        )

        assert result is not None
        assert result["type"] == "task_verification"


@pytest.mark.unit
class TestVerifyChore:
    """Tests for verify_chore function."""

    @pytest.fixture
    async def pending_chore_with_claim(self, patched_verification_db, setup_test_users):
        """Create a chore with a verification claim."""
        user1_id = setup_test_users["user1"]["id"]
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(user1_id),
        )

        # Request verification (creates claim log and workflow)
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(user1_id),
            notes="Completed",
        )

        return await chore_service.get_chore_by_id(chore_id=chore["id"])

    async def test_verify_chore_approve(self, patched_verification_db, pending_chore_with_claim, setup_test_users):
        """Test approving a chore verification."""
        result = await verification_service.verify_chore(
            task_id=pending_chore_with_claim["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),  # Different from claimer
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        assert result["id"] == pending_chore_with_claim["id"]
        assert result["current_state"] == TaskState.COMPLETED

    async def test_verify_chore_reject(self, patched_verification_db, pending_chore_with_claim, setup_test_users):
        """Test rejecting a chore verification."""
        result = await verification_service.verify_chore(
            task_id=pending_chore_with_claim["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.REJECT,
            reason="Not done properly",
        )

        assert result["id"] == pending_chore_with_claim["id"]
        assert result["current_state"] == TaskState.TODO

    async def test_verify_chore_self_verification_fails(
        self, patched_verification_db, pending_chore_with_claim, setup_test_users
    ):
        """Test that claimer cannot verify their own chore."""
        with pytest.raises(ValueError, match="Cannot approve own workflow"):
            await verification_service.verify_chore(
                task_id=pending_chore_with_claim["id"],
                verifier_user_id=str(setup_test_users["user1"]["id"]),  # Same as claimer
                decision=VerificationDecision.APPROVE,
                reason="",
            )

    async def test_verify_chore_no_claim_log_found(self, patched_verification_db, setup_test_users):
        """Test verifying chore with no claim log raises error."""
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        # Create a chore but don't claim it
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1_id,
        )

        # Manually transition to pending (bypassing normal claim flow)
        await chore_service.mark_pending_verification(chore_id=chore["id"])

        with pytest.raises(ValueError, match="No pending verification request for task"):
            await verification_service.verify_chore(
                task_id=chore["id"],
                verifier_user_id=user2_id,
                decision=VerificationDecision.APPROVE,
                reason="",
            )


@pytest.mark.unit
class TestGetPendingVerifications:
    """Tests for get_pending_verifications function."""

    @pytest.fixture
    async def setup_pending_chores(self, patched_verification_db, setup_test_users):
        """Create multiple chores with different states and claims."""
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        user3_id = str(setup_test_users["user3"]["id"])
        # Chore 1: Pending verification claimed by user1
        chore1 = await chore_service.create_chore(
            title="Chore 1",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1_id,
        )
        await verification_service.request_verification(
            chore_id=chore1["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Done",
        )

        # Chore 2: Pending verification claimed by user2
        chore2 = await chore_service.create_chore(
            title="Chore 2",
            description="Test",
            recurrence="0 11 * * *",
            assigned_to=user2_id,
        )
        await verification_service.request_verification(
            chore_id=chore2["id"],
            claimer_user_id=str(setup_test_users["user2"]["id"]),
            notes="Done",
        )

        # Chore 3: TODO state (not pending verification)
        chore3 = await chore_service.create_chore(
            title="Chore 3",
            description="Test",
            recurrence="0 12 * * *",
            assigned_to=user3_id,
        )

        return {"chore1": chore1, "chore2": chore2, "chore3": chore3}

    async def test_get_all_pending_verifications(self, patched_verification_db, setup_pending_chores):
        """Test getting all pending verifications without user filter."""
        result = await verification_service.get_pending_verifications()

        assert len(result) == 2
        assert all(chore["current_state"] == TaskState.PENDING_VERIFICATION for chore in result)

    async def test_get_pending_verifications_excluding_user(
        self, patched_verification_db, setup_pending_chores, setup_test_users
    ):
        """Test getting pending verifications excluding those claimed by specific user."""
        # user1 should only see chores they didn't claim
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user1"]["id"]))

        assert len(result) == 1
        # Should only contain chore2 (claimed by user2)
        assert result[0]["id"] == setup_pending_chores["chore2"]["id"]

    async def test_get_pending_verifications_user_claimed_all(
        self, patched_verification_db, setup_pending_chores, setup_test_users
    ):
        """Test user who claimed all pending chores sees none."""
        # Create scenario where user3 claimed both chores
        chore4 = await chore_service.create_chore(
            title="Chore 4",
            description="Test",
            recurrence="0 13 * * *",
            assigned_to=str(setup_test_users["user3"]["id"]),
        )
        await verification_service.request_verification(
            chore_id=chore4["id"],
            claimer_user_id=str(setup_test_users["user3"]["id"]),
            notes="Done",
        )

        # user3 should not see their own claim
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user3"]["id"]))

        # Should not include chore4
        assert not any(chore["id"] == chore4["id"] for chore in result)

    async def test_get_pending_verifications_empty(self, patched_verification_db):
        """Test getting pending verifications when none exist."""
        result = await verification_service.get_pending_verifications()

        assert result == []


@pytest.mark.unit
class TestVerificationWorkflow:
    """Integration-style tests for the full verification workflow."""

    async def test_full_approval_workflow(self, patched_verification_db, setup_test_users):
        """Test complete workflow: create -> claim -> approve."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Claim completion
        workflow = await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="All done!",
        )

        assert workflow["type"] == "task_verification"
        assert workflow["status"] == "pending"

        # Verify chore state
        chore_after_claim = await chore_service.get_chore_by_id(chore_id=chore["id"])
        assert chore_after_claim["current_state"] == TaskState.PENDING_VERIFICATION

        # Approve verification
        final_chore = await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.APPROVE,
            reason="Verified!",
        )

        assert final_chore["current_state"] == TaskState.COMPLETED

    async def test_full_rejection_workflow(self, patched_verification_db, setup_test_users):
        """Test complete workflow: create -> claim -> reject."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Claim completion
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Done",
        )

        # Reject verification
        final_chore = await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.REJECT,
            reason="Not acceptable",
        )

        assert final_chore["current_state"] == TaskState.TODO


@pytest.mark.unit
class TestVerificationCacheInvalidation:
    """Tests for cache invalidation during verification workflow."""

    @patch("src.modules.tasks.analytics")
    async def test_approve_verification_invalidates_cache(
        self, mock_analytics, patched_verification_db, setup_test_users
    ):
        """Verify cache is invalidated when chore verification is approved."""
        mock_analytics.invalidate_leaderboard_cache = AsyncMock(return_value=None)

        # Create and claim chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Done",
        )

        # Approve verification
        await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        # Verify cache invalidation was called
        mock_analytics.invalidate_leaderboard_cache.assert_called_once()

    @patch("src.modules.tasks.analytics")
    async def test_reject_verification_invalidates_cache(
        self, mock_analytics, patched_verification_db, setup_test_users
    ):
        """Verify cache is invalidated when chore verification is rejected."""
        mock_analytics.invalidate_leaderboard_cache = AsyncMock(return_value=None)

        # Create and claim chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Done",
        )

        # Reject verification
        await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.REJECT,
            reason="Not acceptable",
        )

        # Verify cache invalidation was called
        mock_analytics.invalidate_leaderboard_cache.assert_called_once()

    @patch("src.modules.tasks.analytics.redis_client.keys")
    async def test_verification_succeeds_if_cache_invalidation_fails(
        self, mock_redis_keys, patched_verification_db, setup_test_users
    ):
        """Verify verification succeeds even if cache invalidation fails."""
        # Mock Redis to fail - this tests that internal exception handling in invalidate_leaderboard_cache
        mock_redis_keys.side_effect = Exception("Redis connection error")

        # Create and claim chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Done",
        )

        # Approve verification - should succeed despite cache failure
        result = await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        # Verify chore was still completed successfully
        assert result["current_state"] == TaskState.COMPLETED

        # Verify Redis was accessed (cache invalidation was attempted)
        mock_redis_keys.assert_called_once()


@pytest.mark.unit
class TestVerifyChorePagination:
    """Tests for verify_chore pagination edge cases."""

    async def _create_logs(
        self,
        patched_verification_db,
        count: int,
        chore_id: str = "",
        action: str = "other_action",
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Helper to create multiple log entries."""
        logs = []
        for i in range(count):
            log_data = {
                "task_id": chore_id if action == "claimed_completion" and chore_id else None,
                "user_id": user_id if user_id else None,
                "action": action,
                "notes": f"Log {i}",
                "timestamp": datetime.now().isoformat(),
            }
            log = await patched_verification_db.create_record(collection="task_logs", data=log_data)
            logs.append(log)
        return logs

    async def test_claim_log_on_first_page(self, patched_verification_db, setup_test_users):
        """Test that verify_chore finds claim log on first page with 1 page fetch."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Create 100 other logs
        await self._create_logs(patched_verification_db, 100, chore["id"], action="other_action")

        # Request verification (creates claim log)
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Completed",
        )

        # Verify should succeed - claim log is on first page
        result = await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        assert result["current_state"] == TaskState.COMPLETED

    async def test_claim_log_on_second_page(self, patched_verification_db, setup_test_users):
        """Test that verify_chore correctly finds claim log beyond first page."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Request verification first (creates claim log)
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Completed",
        )

        # Create 500 other logs AFTER claim log (sorted -created, so newer logs come first)
        await self._create_logs(patched_verification_db, 500, chore["id"], action="other_action")

        # Verify should succeed - claim log is on second page
        result = await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        assert result["current_state"] == TaskState.COMPLETED

    async def test_claim_log_on_exact_boundary(self, patched_verification_db, setup_test_users):
        """Test claim log at position 500 (exact page boundary)."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Request verification first
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Completed",
        )

        # Create exactly 499 other logs AFTER (so claim log is at position 500)
        await self._create_logs(patched_verification_db, 499, chore["id"], action="other_action")

        # Verify should succeed
        result = await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=str(setup_test_users["user2"]["id"]),
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        assert result["current_state"] == TaskState.COMPLETED

    async def test_no_claim_log_exists(self, patched_verification_db, setup_test_users):
        """Test that verify_chore raises error when no claim log exists after checking all pages."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Manually transition to pending (bypassing normal claim flow)
        await chore_service.mark_pending_verification(chore_id=chore["id"])

        # Create 600 other logs (spans 2 pages)
        await self._create_logs(patched_verification_db, 600, chore["id"], action="other_action")

        # Verify should raise error - no workflow exists
        with pytest.raises(ValueError, match="No pending verification request for task"):
            await verification_service.verify_chore(
                task_id=chore["id"],
                verifier_user_id=str(setup_test_users["user2"]["id"]),
                decision=VerificationDecision.APPROVE,
                reason="",
            )

    async def test_empty_logs_collection(self, patched_verification_db, setup_test_users):
        """Test that verify_chore raises error when logs collection is empty."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Manually transition to pending (bypassing normal claim flow)
        await chore_service.mark_pending_verification(chore_id=chore["id"])

        # No logs created - empty collection

        # Verify should raise error
        with pytest.raises(ValueError, match="No pending verification request for task"):
            await verification_service.verify_chore(
                task_id=chore["id"],
                verifier_user_id=str(setup_test_users["user2"]["id"]),
                decision=VerificationDecision.APPROVE,
                reason="",
            )

    async def test_self_verification_prevented(self, patched_verification_db, setup_test_users):
        """Test that claimer cannot verify their own chore (existing behavior verification)."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        # Request verification
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user1"]["id"]),
            notes="Completed",
        )

        # Create 500 other logs to ensure pagination works even with self-verification check
        await self._create_logs(patched_verification_db, 500, chore["id"], action="other_action")

        # Self-verification should fail (workflow layer prevents self-approval)
        with pytest.raises(ValueError, match="Cannot approve own workflow"):
            await verification_service.verify_chore(
                task_id=chore["id"],
                verifier_user_id=str(setup_test_users["user1"]["id"]),  # Same as claimer
                decision=VerificationDecision.APPROVE,
                reason="",
            )


@pytest.mark.unit
class TestGetPendingVerificationsPagination:
    """Tests for get_pending_verifications pagination edge cases."""

    async def _create_chore_with_claim(
        self, patched_verification_db: DatabaseClient, *, title: str, claimer_user_id: str
    ) -> dict[str, Any]:
        """Helper to create a chore and claim it."""
        chore = await chore_service.create_chore(
            title=title,
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=claimer_user_id,
        )
        await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=claimer_user_id,
            notes="Done",
        )
        return chore

    async def _create_logs(
        self,
        patched_verification_db: DatabaseClient,
        *,
        count: int,
        chore_id: str = "",
        action: str = "other_action",
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Helper to create multiple log entries."""
        logs = []
        for i in range(count):
            log_data = {
                "task_id": chore_id if action == "claimed_completion" and chore_id else None,
                "user_id": user_id if user_id else None,
                "action": action,
                "notes": f"Log {i}",
                "timestamp": datetime.now().isoformat(),
            }
            log = await patched_verification_db.create_record(collection="task_logs", data=log_data)
            logs.append(log)
        return logs

    async def _create_chore(
        self,
        patched_verification_db: DatabaseClient,
        user_id: str,
        *,
        title: str = "Test Chore",
        description: str = "Test",
        recurrence: str = "0 10 * * *",
    ) -> dict[str, Any]:
        """Helper to create a chore with real user ID."""
        return await chore_service.create_chore(
            title=title,
            description=description,
            recurrence=recurrence,
            assigned_to=user_id,
        )

    async def test_no_user_id_filter(self, patched_verification_db, setup_test_users):
        """Test that without user_id filter, all pending chores are returned."""
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        user3_id = str(setup_test_users["user3"]["id"])
        _chore1 = await self._create_chore_with_claim(
            patched_verification_db, title="Chore 1", claimer_user_id=user1_id
        )
        chore2 = await self._create_chore_with_claim(patched_verification_db, title="Chore 2", claimer_user_id=user2_id)
        chore3 = await self._create_chore_with_claim(patched_verification_db, title="Chore 3", claimer_user_id=user3_id)

        # Get all pending verifications
        result = await verification_service.get_pending_verifications()

        assert len(result) == 3
        result_ids = {c["id"] for c in result}
        assert _chore1["id"] in result_ids
        assert chore2["id"] in result_ids
        assert chore3["id"] in result_ids

    async def test_user_id_filter_with_logs_on_multiple_pages(self, patched_verification_db, setup_test_users):
        """Test filtering correctly when logs span multiple pages."""
        # Create 2 pending chores
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        _chore1 = await self._create_chore_with_claim(
            patched_verification_db, title="Chore 1", claimer_user_id=user1_id
        )
        chore2 = await self._create_chore_with_claim(patched_verification_db, title="Chore 2", claimer_user_id=user2_id)

        # Create 500 other logs to force pagination
        await self._create_logs(patched_verification_db, count=500)

        # user1 should only see chore2 (claimed by user2)
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user1"]["id"]))

        assert len(result) == 1
        assert result[0]["id"] == chore2["id"]

    async def test_user_claimed_chore_on_page_2(self, patched_verification_db, setup_test_users):
        """Test that chore claimed by user on page 2 is correctly excluded."""
        # Create chore claimed by user1
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        _chore1 = await self._create_chore_with_claim(
            patched_verification_db, title="Chore 1", claimer_user_id=user1_id
        )

        # Create 500 other logs AFTER claim log (so claim log ends up on page 2)
        await self._create_logs(patched_verification_db, count=500, chore_id="other_chore")

        # Create another chore claimed by user2
        chore2 = await self._create_chore_with_claim(patched_verification_db, title="Chore 2", claimer_user_id=user2_id)

        # user1 should only see chore2
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user1"]["id"]))

        assert len(result) == 1
        assert result[0]["id"] == chore2["id"]

    async def test_all_chores_claimed_by_user(self, patched_verification_db, setup_test_users):
        """Test that user who claimed all pending chores sees empty list."""
        # Create 3 chores all claimed by user1
        user1_id = str(setup_test_users["user1"]["id"])
        await self._create_chore_with_claim(patched_verification_db, title="Chore 1", claimer_user_id=user1_id)
        await self._create_chore_with_claim(patched_verification_db, title="Chore 2", claimer_user_id=user1_id)
        await self._create_chore_with_claim(patched_verification_db, title="Chore 3", claimer_user_id=user1_id)

        # user1 should see no chores
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user1"]["id"]))

        assert result == []

    async def test_no_chores_in_pending_verification(self, patched_verification_db, setup_test_users):
        """Test that empty list is returned when no chores are pending verification."""
        # Create a chore but don't claim it (stays in TODO state)
        await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        result = await verification_service.get_pending_verifications()

        assert result == []

    async def test_logs_on_exact_page_boundary(self, patched_verification_db, setup_test_users):
        """Test handling of claim log at exact page boundary (position 500)."""
        # Create chore claimed by user1
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        _chore1 = await self._create_chore_with_claim(
            patched_verification_db, title="Chore 1", claimer_user_id=user1_id
        )

        # Create exactly 499 other logs AFTER (so claim log is at position 500)
        await self._create_logs(patched_verification_db, count=499, chore_id="other_chore")

        # Create another chore claimed by user2
        chore2 = await self._create_chore_with_claim(patched_verification_db, title="Chore 2", claimer_user_id=user2_id)

        # user1 should only see chore2
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user1"]["id"]))

        assert len(result) == 1
        assert result[0]["id"] == chore2["id"]

    async def test_large_log_collection(self, patched_verification_db, setup_test_users):
        """Test correct filtering with 1000+ logs."""
        # Create 3 pending chores
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        user3_id = str(setup_test_users["user3"]["id"])
        _chore1 = await self._create_chore_with_claim(
            patched_verification_db, title="Chore 1", claimer_user_id=user1_id
        )
        chore2 = await self._create_chore_with_claim(patched_verification_db, title="Chore 2", claimer_user_id=user2_id)
        chore3 = await self._create_chore_with_claim(patched_verification_db, title="Chore 3", claimer_user_id=user3_id)

        # Create 1000 other logs
        await self._create_logs(patched_verification_db, count=1000, chore_id="other_chore")

        # user1 should see chore2 and chore3
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user1"]["id"]))

        assert len(result) == 2
        result_ids = {c["id"] for c in result}
        assert chore2["id"] in result_ids
        assert chore3["id"] in result_ids
        assert _chore1["id"] not in result_ids

    async def test_many_pending_chores_batched_queries(self, patched_verification_db, monkeypatch, setup_test_users):
        """Test that many pending chores are processed in batches.

        This test verifies that batching is used by checking number of list_records calls.
        """
        # Use smaller batch size for testing
        monkeypatch.setattr(verification_service, "CHORE_ID_BATCH_SIZE", 5)

        # Create 12 pending chores (exceeds batch size of 5, requires 3 batches)
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        user1_chores = []
        user2_chores = []
        for i in range(12):
            # Alternate between user1 and user2 claiming chores
            claimer = user1_id if i % 2 == 0 else user2_id
            chore = await self._create_chore_with_claim(
                patched_verification_db, title=f"Chore {i}", claimer_user_id=claimer
            )
            if claimer == user1_id:
                user1_chores.append(chore)
            else:
                user2_chores.append(chore)

        # Track list_records calls
        original_list_records = db_client_module.list_records
        call_count = 0
        filter_queries = []

        async def tracking_list_records(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "filter_query" in kwargs:
                filter_queries.append(kwargs["filter_query"])
            return await original_list_records(*args, **kwargs)

        monkeypatch.setattr(db_client_module, "list_records", tracking_list_records)

        # Reset counter after setup
        call_count = 0
        filter_queries.clear()

        # user1 should only see chores claimed by user2 (6 chores)
        result = await verification_service.get_pending_verifications(user_id=str(setup_test_users["user1"]["id"]))

        assert len(result) == 6
        result_ids = {c["id"] for c in result}
        # All user2's chores should be visible to user1
        for chore in user2_chores:
            assert chore["id"] in result_ids
        # None of user1's chores should be visible
        for chore in user1_chores:
            assert chore["id"] not in result_ids

        # Verify batching occurred: 12 chores / 5 per batch = 3 batches
        # Each batch makes at least 1 call to list_records for logs
        # Note: First call is to get chores by state (in chore_service.get_chores)
        # Then we expect 3 batches of log queries
        log_query_calls = [q for q in filter_queries if "claimed_completion" in q]
        assert len(log_query_calls) >= 3, f"Expected at least 3 batched log queries, got {len(log_query_calls)}"


@pytest.mark.unit
class TestVerificationWorkflowIntegration:
    """Tests for workflow_service integration with verification_service."""

    async def test_request_verification_creates_workflow(self, patched_verification_db, setup_test_users):
        """Test that request_verification creates a workflow with correct type."""
        user1_id = str(setup_test_users["user1"]["id"])
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1_id,
        )

        workflow = await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=user1_id,
            notes="Done",
        )

        # Verify workflow was created
        assert workflow["type"] == "task_verification"
        assert workflow["status"] == "pending"
        assert workflow["requester_user_id"] == user1_id
        assert workflow["target_id"] == chore["id"]

    async def test_request_verification_includes_metadata(self, patched_verification_db, setup_test_users):
        """Test that request_verification includes is_swap and notes in workflow metadata."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=str(setup_test_users["user1"]["id"]),
        )

        workflow = await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=str(setup_test_users["user2"]["id"]),
            notes="I did this chore for user1",
            is_swap=True,
        )

        # Verify metadata includes is_swap and notes
        assert workflow["metadata"]["is_swap"] is True
        assert workflow["metadata"]["notes"] == "I did this chore for user1"

    async def test_verify_chore_resolves_workflow(self, patched_verification_db, setup_test_users):
        """Test that verify_chore resolves the workflow."""
        user1_id = str(setup_test_users["user1"]["id"])
        user2_id = str(setup_test_users["user2"]["id"])
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1_id,
        )

        # Request verification
        workflow = await verification_service.request_verification(
            chore_id=chore["id"],
            claimer_user_id=user1_id,
            notes="Done",
        )

        # Verify chore
        await verification_service.verify_chore(
            task_id=chore["id"],
            verifier_user_id=user2_id,
            decision=VerificationDecision.APPROVE,
            reason="Looks good",
        )

        # Verify workflow was resolved
        updated_workflow = await verification_service.get_pending_verification_workflow(chore_id=chore["id"])
        assert updated_workflow is None, "Workflow should no longer be pending"

        # Get the workflow by ID to check its status
        workflow_records = await patched_verification_db.list_records(
            collection="workflows",
            filter_query=f'id = "{workflow["id"]}"',
        )
        assert workflow_records[0]["status"] == "approved"
        assert workflow_records[0]["resolver_user_id"] == user2_id
