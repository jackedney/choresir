"""Unit tests for deletion_service module."""

from datetime import datetime, timedelta

import pytest

from src.domain.chore import ChoreState
from src.services import chore_service, deletion_service


@pytest.fixture
def patched_deletion_db(monkeypatch, in_memory_db):
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
class TestRequestChoreDeletion:
    """Tests for request_chore_deletion function."""

    @pytest.fixture
    async def todo_chore(self, patched_deletion_db):
        """Create a chore in TODO state."""
        return await chore_service.create_chore(
            title="Test Chore",
            description="Test chore",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

    async def test_request_deletion_success(self, patched_deletion_db, todo_chore):
        """Test requesting deletion for a chore creates log entry."""
        log_record = await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id="user1",
            reason="No longer needed",
        )

        # Verify log was created
        assert log_record["chore_id"] == todo_chore["id"]
        assert log_record["user_id"] == "user1"
        assert log_record["action"] == "deletion_requested"
        assert "No longer needed" in log_record["notes"]

    async def test_request_deletion_without_reason(self, patched_deletion_db, todo_chore):
        """Test requesting deletion without reason."""
        log_record = await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id="user1",
        )

        assert log_record["action"] == "deletion_requested"
        assert log_record["notes"] == ""

    async def test_request_deletion_chore_not_found(self, patched_deletion_db):
        """Test requesting deletion for non-existent chore raises error."""
        with pytest.raises(KeyError):
            await deletion_service.request_chore_deletion(
                chore_id="nonexistent_id",
                requester_user_id="user1",
            )

    async def test_request_deletion_archived_chore_fails(self, patched_deletion_db, todo_chore):
        """Test requesting deletion for already archived chore fails."""
        # Archive the chore
        await patched_deletion_db.update_record(
            collection="chores",
            record_id=todo_chore["id"],
            data={"current_state": ChoreState.ARCHIVED},
        )

        with pytest.raises(ValueError, match="already archived"):
            await deletion_service.request_chore_deletion(
                chore_id=todo_chore["id"],
                requester_user_id="user1",
            )

    async def test_request_deletion_duplicate_request_fails(self, patched_deletion_db, todo_chore):
        """Test requesting deletion when pending request exists fails."""
        # Create first deletion request
        await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id="user1",
        )

        # Second request should fail
        with pytest.raises(ValueError, match="already has a pending deletion request"):
            await deletion_service.request_chore_deletion(
                chore_id=todo_chore["id"],
                requester_user_id="user2",
            )


@pytest.mark.unit
class TestApproveChoreDeletion:
    """Tests for approve_chore_deletion function."""

    @pytest.fixture
    async def chore_with_pending_deletion(self, patched_deletion_db):
        """Create a chore with a pending deletion request."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Create deletion request
        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
            reason="Want to remove",
        )

        return await chore_service.get_chore_by_id(chore_id=chore["id"])

    async def test_approve_deletion_success(self, patched_deletion_db, chore_with_pending_deletion):
        """Test approving a deletion request archives the chore."""
        result = await deletion_service.approve_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            approver_user_id="user2",  # Different from requester
            reason="Approved",
        )

        assert result["id"] == chore_with_pending_deletion["id"]
        assert result["current_state"] == ChoreState.ARCHIVED

    async def test_approve_deletion_self_approval_fails(self, patched_deletion_db, chore_with_pending_deletion):
        """Test that requester cannot approve their own deletion request."""
        with pytest.raises(PermissionError, match="cannot approve their own deletion request"):
            await deletion_service.approve_chore_deletion(
                chore_id=chore_with_pending_deletion["id"],
                approver_user_id="user1",  # Same as requester
                reason="",
            )

    async def test_approve_deletion_no_pending_request(self, patched_deletion_db):
        """Test approving deletion with no pending request fails."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        with pytest.raises(ValueError, match="No pending deletion request"):
            await deletion_service.approve_chore_deletion(
                chore_id=chore["id"],
                approver_user_id="user2",
            )

    async def test_approve_deletion_creates_log(self, patched_deletion_db, chore_with_pending_deletion):
        """Test approving deletion creates an approval log."""
        await deletion_service.approve_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            approver_user_id="user2",
            reason="Looks good",
        )

        # Check that approval log was created
        logs = await patched_deletion_db.list_records(
            collection="logs",
            filter_query=f'chore_id = "{chore_with_pending_deletion["id"]}" && action = "deletion_approved"',
        )

        assert len(logs) == 1
        assert logs[0]["user_id"] == "user2"
        assert "Looks good" in logs[0]["notes"]


@pytest.mark.unit
class TestRejectChoreDeletion:
    """Tests for reject_chore_deletion function."""

    @pytest.fixture
    async def chore_with_pending_deletion(self, patched_deletion_db):
        """Create a chore with a pending deletion request."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
        )

        return await chore_service.get_chore_by_id(chore_id=chore["id"])

    async def test_reject_deletion_success(self, patched_deletion_db, chore_with_pending_deletion):
        """Test rejecting a deletion request creates rejection log."""
        result = await deletion_service.reject_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            rejecter_user_id="user2",
            reason="Still needed",
        )

        assert result["action"] == "deletion_rejected"
        assert result["user_id"] == "user2"
        assert "Still needed" in result["notes"]

    async def test_reject_deletion_chore_remains_active(self, patched_deletion_db, chore_with_pending_deletion):
        """Test that rejecting deletion leaves chore active (not archived)."""
        await deletion_service.reject_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            rejecter_user_id="user2",
        )

        chore = await chore_service.get_chore_by_id(chore_id=chore_with_pending_deletion["id"])
        assert chore["current_state"] != ChoreState.ARCHIVED

    async def test_reject_deletion_no_pending_request(self, patched_deletion_db):
        """Test rejecting deletion with no pending request fails."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        with pytest.raises(ValueError, match="No pending deletion request"):
            await deletion_service.reject_chore_deletion(
                chore_id=chore["id"],
                rejecter_user_id="user2",
            )

    async def test_reject_by_requester_allowed(self, patched_deletion_db, chore_with_pending_deletion):
        """Test that requester CAN reject their own request (cancel it)."""
        # This is allowed - a requester should be able to cancel their own request
        result = await deletion_service.reject_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            rejecter_user_id="user1",  # Same as requester - allowed for cancel
            reason="Changed my mind",
        )

        assert result["action"] == "deletion_rejected"


@pytest.mark.unit
class TestGetPendingDeletionRequest:
    """Tests for get_pending_deletion_request function."""

    async def test_no_pending_request(self, patched_deletion_db):
        """Test returns None when no pending request exists."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        result = await deletion_service.get_pending_deletion_request(chore_id=chore["id"])
        assert result is None

    async def test_pending_request_exists(self, patched_deletion_db):
        """Test returns request when one is pending."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
        )

        result = await deletion_service.get_pending_deletion_request(chore_id=chore["id"])
        assert result is not None
        assert result["action"] == "deletion_requested"
        assert result["chore_id"] == chore["id"]

    async def test_resolved_request_not_returned(self, patched_deletion_db):
        """Test returns None after request is resolved."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
        )

        # Approve the request
        await deletion_service.approve_chore_deletion(
            chore_id=chore["id"],
            approver_user_id="user2",
        )

        # Should no longer be pending
        result = await deletion_service.get_pending_deletion_request(chore_id=chore["id"])
        assert result is None

    async def test_expired_request_not_returned(self, patched_deletion_db, monkeypatch):
        """Test returns None for expired request (>48 hours old)."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Create an old deletion request
        old_timestamp = (datetime.now() - timedelta(hours=49)).isoformat()
        await patched_deletion_db.create_record(
            collection="logs",
            data={
                "chore_id": chore["id"],
                "user_id": "user1",
                "action": "deletion_requested",
                "notes": "",
                "timestamp": old_timestamp,
            },
        )

        result = await deletion_service.get_pending_deletion_request(chore_id=chore["id"])
        assert result is None


@pytest.mark.unit
class TestDeletionWorkflow:
    """Integration-style tests for the full deletion workflow."""

    async def test_full_approval_workflow(self, patched_deletion_db):
        """Test complete workflow: request -> approve -> archived."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Request deletion
        request_log = await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
            reason="No longer needed",
        )

        assert request_log["action"] == "deletion_requested"

        # Verify pending request exists
        pending = await deletion_service.get_pending_deletion_request(chore_id=chore["id"])
        assert pending is not None

        # Approve deletion
        final_chore = await deletion_service.approve_chore_deletion(
            chore_id=chore["id"],
            approver_user_id="user2",
            reason="Agreed",
        )

        assert final_chore["current_state"] == ChoreState.ARCHIVED

        # Verify no pending request
        pending = await deletion_service.get_pending_deletion_request(chore_id=chore["id"])
        assert pending is None

    async def test_full_rejection_workflow(self, patched_deletion_db):
        """Test complete workflow: request -> reject -> still active."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Request deletion
        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
        )

        # Reject deletion
        await deletion_service.reject_chore_deletion(
            chore_id=chore["id"],
            rejecter_user_id="user2",
            reason="Still needed",
        )

        # Chore should still be active
        final_chore = await chore_service.get_chore_by_id(chore_id=chore["id"])
        assert final_chore["current_state"] != ChoreState.ARCHIVED

    async def test_new_request_after_rejection(self, patched_deletion_db):
        """Test that new deletion request can be made after rejection."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # First request
        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
        )

        # Reject
        await deletion_service.reject_chore_deletion(
            chore_id=chore["id"],
            rejecter_user_id="user2",
        )

        # New request should succeed
        new_request = await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user2",
            reason="Trying again",
        )

        assert new_request["action"] == "deletion_requested"


@pytest.mark.unit
class TestExpireOldDeletionRequests:
    """Tests for expire_old_deletion_requests function."""

    async def test_expires_old_requests(self, patched_deletion_db):
        """Test that old deletion requests are expired."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Create an old deletion request
        old_timestamp = (datetime.now() - timedelta(hours=49)).isoformat()
        await patched_deletion_db.create_record(
            collection="logs",
            data={
                "chore_id": chore["id"],
                "user_id": "user1",
                "action": "deletion_requested",
                "notes": "",
                "timestamp": old_timestamp,
            },
        )

        # Run expiry
        count = await deletion_service.expire_old_deletion_requests()

        # Should have expired 1 request
        assert count == 1

        # Check rejection log was created
        logs = await patched_deletion_db.list_records(
            collection="logs",
            filter_query=f'chore_id = "{chore["id"]}" && action = "deletion_rejected"',
        )

        assert len(logs) == 1
        assert "Auto-expired" in logs[0]["notes"]

    async def test_does_not_expire_recent_requests(self, patched_deletion_db):
        """Test that recent deletion requests are not expired."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Create a recent deletion request
        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id="user1",
        )

        # Run expiry
        count = await deletion_service.expire_old_deletion_requests()

        # Should not have expired any requests
        assert count == 0

        # Request should still be pending
        pending = await deletion_service.get_pending_deletion_request(chore_id=chore["id"])
        assert pending is not None

    async def test_does_not_expire_already_resolved_requests(self, patched_deletion_db):
        """Test that already resolved requests are not double-expired."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

        # Create an old deletion request
        old_timestamp = (datetime.now() - timedelta(hours=49)).isoformat()
        _ = await patched_deletion_db.create_record(
            collection="logs",
            data={
                "chore_id": chore["id"],
                "user_id": "user1",
                "action": "deletion_requested",
                "notes": "",
                "timestamp": old_timestamp,
            },
        )

        # Create a rejection log for it (already resolved)
        await patched_deletion_db.create_record(
            collection="logs",
            data={
                "chore_id": chore["id"],
                "user_id": "user2",
                "action": "deletion_rejected",
                "notes": "Already rejected",
                "timestamp": (datetime.now() - timedelta(hours=48)).isoformat(),
            },
        )

        # Run expiry
        count = await deletion_service.expire_old_deletion_requests()

        # Should not have expired anything (already resolved)
        assert count == 0


@pytest.mark.unit
class TestGetAllPendingDeletionRequests:
    """Tests for get_all_pending_deletion_requests function."""

    async def test_returns_empty_when_none_pending(self, patched_deletion_db):
        """Test returns empty list when no pending requests."""
        result = await deletion_service.get_all_pending_deletion_requests()
        assert result == []

    async def test_returns_pending_requests(self, patched_deletion_db):
        """Test returns all pending requests."""
        # Create two chores with pending deletions
        chore1 = await chore_service.create_chore(
            title="Chore 1",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        chore2 = await chore_service.create_chore(
            title="Chore 2",
            description="Test",
            recurrence="0 11 * * *",
            assigned_to="user2",
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore1["id"],
            requester_user_id="user1",
        )
        await deletion_service.request_chore_deletion(
            chore_id=chore2["id"],
            requester_user_id="user2",
        )

        result = await deletion_service.get_all_pending_deletion_requests()

        assert len(result) == 2
        # Should be enriched with chore titles
        titles = [r["chore_title"] for r in result]
        assert "Chore 1" in titles
        assert "Chore 2" in titles

    async def test_excludes_resolved_requests(self, patched_deletion_db):
        """Test excludes already resolved requests."""
        chore1 = await chore_service.create_chore(
            title="Chore 1",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        chore2 = await chore_service.create_chore(
            title="Chore 2",
            description="Test",
            recurrence="0 11 * * *",
            assigned_to="user2",
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore1["id"],
            requester_user_id="user1",
        )
        await deletion_service.request_chore_deletion(
            chore_id=chore2["id"],
            requester_user_id="user2",
        )

        # Approve one of them
        await deletion_service.approve_chore_deletion(
            chore_id=chore1["id"],
            approver_user_id="user3",
        )

        result = await deletion_service.get_all_pending_deletion_requests()

        assert len(result) == 1
        assert result[0]["chore_title"] == "Chore 2"
