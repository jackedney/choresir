"""Unit tests for deletion_service module."""

import pytest

from src.domain.chore import ChoreState
from src.services import chore_service, deletion_service, workflow_service


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


@pytest.fixture
async def user1(patched_deletion_db):
    """Create a test user."""
    return await patched_deletion_db.create_record(
        collection="members",
        data={
            "phone": "+1234567890",
            "name": "User One",
            "role": "member",
            "status": "active",
        },
    )


@pytest.fixture
async def user2(patched_deletion_db):
    """Create another test user."""
    return await patched_deletion_db.create_record(
        collection="members",
        data={
            "phone": "+1987654321",
            "name": "User Two",
            "role": "member",
            "status": "active",
        },
    )


@pytest.mark.unit
class TestRequestChoreDeletion:
    """Tests for request_chore_deletion function."""

    @pytest.fixture
    async def todo_chore(self, patched_deletion_db, user1):
        """Create a chore in TODO state."""
        return await chore_service.create_chore(
            title="Test Chore",
            description="Test chore",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

    async def test_request_deletion_success(self, patched_deletion_db, user1, todo_chore):
        """Test requesting deletion for a chore creates workflow and log."""
        workflow = await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id=user1["id"],
            reason="No longer needed",
        )

        # Verify workflow was created
        assert workflow["type"] == workflow_service.WorkflowType.DELETION_APPROVAL.value
        assert workflow["requester_user_id"] == user1["id"]
        assert workflow["requester_name"] == user1["name"]
        assert workflow["target_id"] == todo_chore["id"]
        assert workflow["target_title"] == todo_chore["title"]
        assert workflow["status"] == workflow_service.WorkflowStatus.PENDING.value

        # Verify log was created
        logs = await patched_deletion_db.list_records(
            collection="logs",
            filter_query=f'chore_id = "{todo_chore["id"]}" && action = "deletion_requested"',
        )
        assert len(logs) == 1
        assert logs[0]["user_id"] == user1["id"]
        assert "No longer needed" in logs[0]["notes"]

    async def test_request_deletion_without_reason(self, patched_deletion_db, user1, todo_chore):
        """Test requesting deletion without reason."""
        workflow = await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id=user1["id"],
        )

        assert workflow["type"] == workflow_service.WorkflowType.DELETION_APPROVAL.value
        assert workflow["status"] == workflow_service.WorkflowStatus.PENDING.value

        # Verify log was created
        logs = await patched_deletion_db.list_records(
            collection="logs",
            filter_query=f'chore_id = "{todo_chore["id"]}" && action = "deletion_requested"',
        )
        assert logs[0]["notes"] == ""

    async def test_request_deletion_chore_not_found(self, patched_deletion_db, user1):
        """Test requesting deletion for non-existent chore raises error."""
        with pytest.raises(KeyError):
            await deletion_service.request_chore_deletion(
                chore_id="nonexistent_id",
                requester_user_id=user1["id"],
            )

    async def test_request_deletion_archived_chore_fails(self, patched_deletion_db, user1, todo_chore):
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
                requester_user_id=user1["id"],
            )

    async def test_request_deletion_duplicate_request_fails(self, patched_deletion_db, user1, user2, todo_chore):
        """Test requesting deletion when pending request exists fails."""
        # Create first deletion request
        await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id=user1["id"],
        )

        # Second request should fail
        with pytest.raises(ValueError, match="already has a pending deletion request"):
            await deletion_service.request_chore_deletion(
                chore_id=todo_chore["id"],
                requester_user_id=user2["id"],
            )


@pytest.mark.unit
class TestApproveChoreDeletion:
    """Tests for approve_chore_deletion function."""

    @pytest.fixture
    async def chore_with_pending_deletion(self, patched_deletion_db, user1, user2):
        """Create a chore with a pending deletion workflow."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        # Create deletion workflow
        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user1["id"],
            reason="Want to remove",
        )

        return await chore_service.get_chore_by_id(chore_id=chore["id"])

    async def test_approve_deletion_success(self, patched_deletion_db, user2, chore_with_pending_deletion):
        """Test approving a deletion request archives chore."""
        result = await deletion_service.approve_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            approver_user_id=user2["id"],
            reason="Approved",
        )

        assert result["id"] == chore_with_pending_deletion["id"]
        assert result["current_state"] == ChoreState.ARCHIVED

        # Verify workflow was resolved
        workflows = await patched_deletion_db.list_records(
            collection="workflows",
            filter_query=f'target_id = "{chore_with_pending_deletion["id"]}"',
        )
        assert len(workflows) == 1
        assert workflows[0]["status"] == workflow_service.WorkflowStatus.APPROVED.value
        assert workflows[0]["resolver_user_id"] == user2["id"]

        # Verify log was created
        logs = await patched_deletion_db.list_records(
            collection="logs",
            filter_query=f'chore_id = "{chore_with_pending_deletion["id"]}" && action = "deletion_approved"',
        )
        assert len(logs) == 1
        assert logs[0]["user_id"] == user2["id"]

    async def test_approve_deletion_self_approval_fails(self, patched_deletion_db, user1, chore_with_pending_deletion):
        """Test that requester cannot approve their own deletion request."""
        with pytest.raises(ValueError, match="Cannot approve own workflow"):
            await deletion_service.approve_chore_deletion(
                chore_id=chore_with_pending_deletion["id"],
                approver_user_id=user1["id"],
                reason="",
            )

    async def test_approve_deletion_no_pending_request(self, patched_deletion_db, user1, user2):
        """Test approving deletion with no pending request fails."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        with pytest.raises(ValueError, match="No pending deletion request"):
            await deletion_service.approve_chore_deletion(
                chore_id=chore["id"],
                approver_user_id=user2["id"],
            )


@pytest.mark.unit
class TestRejectChoreDeletion:
    """Tests for reject_chore_deletion function."""

    @pytest.fixture
    async def chore_with_pending_deletion(self, patched_deletion_db, user1):
        """Create a chore with a pending deletion workflow."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user1["id"],
        )

        return await chore_service.get_chore_by_id(chore_id=chore["id"])

    async def test_reject_deletion_success(self, patched_deletion_db, user2, chore_with_pending_deletion):
        """Test rejecting a deletion request creates rejection log."""
        result = await deletion_service.reject_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            rejecter_user_id=user2["id"],
            reason="Still needed",
        )

        assert result["action"] == "deletion_rejected"
        assert result["user_id"] == user2["id"]
        assert "Still needed" in result["notes"]

        # Verify workflow was resolved
        workflows = await patched_deletion_db.list_records(
            collection="workflows",
            filter_query=f'target_id = "{chore_with_pending_deletion["id"]}"',
        )
        assert len(workflows) == 1
        assert workflows[0]["status"] == workflow_service.WorkflowStatus.REJECTED.value

    async def test_reject_deletion_chore_remains_active(self, patched_deletion_db, user2, chore_with_pending_deletion):
        """Test that rejecting deletion leaves chore active (not archived)."""
        await deletion_service.reject_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            rejecter_user_id=user2["id"],
        )

        chore = await chore_service.get_chore_by_id(chore_id=chore_with_pending_deletion["id"])
        assert chore["current_state"] != ChoreState.ARCHIVED

    async def test_reject_deletion_no_pending_request(self, patched_deletion_db, user1, user2):
        """Test rejecting deletion with no pending request fails."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        with pytest.raises(ValueError, match="No pending deletion request"):
            await deletion_service.reject_chore_deletion(
                chore_id=chore["id"],
                rejecter_user_id=user2["id"],
            )

    async def test_reject_by_requester_allowed(self, patched_deletion_db, user1, chore_with_pending_deletion):
        """Test that requester CAN reject their own request (cancel it)."""
        result = await deletion_service.reject_chore_deletion(
            chore_id=chore_with_pending_deletion["id"],
            rejecter_user_id=user1["id"],
            reason="Changed my mind",
        )

        assert result["action"] == "deletion_rejected"


@pytest.mark.unit
class TestGetPendingDeletionWorkflow:
    """Tests for get_pending_deletion_workflow function."""

    async def test_no_pending_workflow(self, patched_deletion_db, user1):
        """Test returns None when no pending workflow exists."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        result = await deletion_service.get_pending_deletion_workflow(chore_id=chore["id"])
        assert result is None

    async def test_pending_workflow_exists(self, patched_deletion_db, user1):
        """Test returns workflow when one is pending."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user1["id"],
        )

        result = await deletion_service.get_pending_deletion_workflow(chore_id=chore["id"])
        assert result is not None
        assert result["type"] == workflow_service.WorkflowType.DELETION_APPROVAL.value
        assert result["target_id"] == chore["id"]

    async def test_resolved_workflow_not_returned(self, patched_deletion_db, user1, user2):
        """Test returns None after workflow is resolved."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user1["id"],
        )

        # Approve the workflow
        await deletion_service.approve_chore_deletion(
            chore_id=chore["id"],
            approver_user_id=user2["id"],
        )

        # Should no longer be pending
        result = await deletion_service.get_pending_deletion_workflow(chore_id=chore["id"])
        assert result is None


@pytest.mark.unit
class TestDeletionWorkflow:
    """Integration-style tests for the full deletion workflow."""

    async def test_full_approval_workflow(self, patched_deletion_db, user1, user2):
        """Test complete workflow: request -> approve -> archived."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        # Request deletion
        workflow = await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user1["id"],
            reason="No longer needed",
        )

        assert workflow["type"] == workflow_service.WorkflowType.DELETION_APPROVAL.value

        # Verify pending workflow exists
        pending = await deletion_service.get_pending_deletion_workflow(chore_id=chore["id"])
        assert pending is not None

        # Approve deletion
        final_chore = await deletion_service.approve_chore_deletion(
            chore_id=chore["id"],
            approver_user_id=user2["id"],
            reason="Agreed",
        )

        assert final_chore["current_state"] == ChoreState.ARCHIVED

        # Verify no pending workflow
        pending = await deletion_service.get_pending_deletion_workflow(chore_id=chore["id"])
        assert pending is None

    async def test_full_rejection_workflow(self, patched_deletion_db, user1, user2):
        """Test complete workflow: request -> reject -> still active."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Workflow",
            description="Full test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        # Request deletion
        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user1["id"],
        )

        # Reject deletion
        await deletion_service.reject_chore_deletion(
            chore_id=chore["id"],
            rejecter_user_id=user2["id"],
            reason="Still needed",
        )

        # Chore should still be active
        final_chore = await chore_service.get_chore_by_id(chore_id=chore["id"])
        assert final_chore["current_state"] != ChoreState.ARCHIVED

    async def test_new_request_after_rejection(self, patched_deletion_db, user1, user2):
        """Test that new deletion request can be made after rejection."""
        # Create chore
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to=user1["id"],
        )

        # First request
        await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user1["id"],
        )

        # Reject
        await deletion_service.reject_chore_deletion(
            chore_id=chore["id"],
            rejecter_user_id=user2["id"],
        )

        # New request should succeed
        new_request = await deletion_service.request_chore_deletion(
            chore_id=chore["id"],
            requester_user_id=user2["id"],
            reason="Trying again",
        )

        assert new_request["type"] == workflow_service.WorkflowType.DELETION_APPROVAL.value
