"""Unit tests for workflow_service module."""

from datetime import datetime, timedelta

import pytest

from src.services import workflow_service


@pytest.fixture
def patched_workflow_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""
    monkeypatch.setattr("src.services.workflow_service.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.services.workflow_service.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.services.workflow_service.db_client.list_records", in_memory_db.list_records)
    return in_memory_db


class TestCreateWorkflow:
    """Test creating workflows."""

    @pytest.mark.asyncio
    async def test_creates_deletion_approval_workflow(
        self,
        patched_workflow_db,
    ):
        """Creates a deletion approval workflow."""
        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
        )

        assert workflow["type"] == "deletion_approval"
        assert workflow["status"] == "pending"
        assert workflow["requester_user_id"] == "user123"
        assert workflow["requester_name"] == "Alice"
        assert workflow["target_id"] == "chore456"
        assert workflow["target_title"] == "Wash Dishes"

    @pytest.mark.asyncio
    async def test_creates_chore_verification_workflow(
        self,
        patched_workflow_db,
    ):
        """Creates a chore verification workflow."""
        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.CHORE_VERIFICATION,
            requester_user_id="user789",
            requester_name="Bob",
            target_id="chore999",
            target_title="Take Out Trash",
        )

        assert workflow["type"] == "chore_verification"
        assert workflow["status"] == "pending"

    @pytest.mark.asyncio
    async def test_creates_personal_verification_workflow(
        self,
        patched_workflow_db,
    ):
        """Creates a personal verification workflow."""
        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.PERSONAL_VERIFICATION,
            requester_user_id="user456",
            requester_name="Charlie",
            target_id="personal_chore123",
            target_title="Buy groceries",
        )

        assert workflow["type"] == "personal_verification"
        assert workflow["status"] == "pending"

    @pytest.mark.asyncio
    async def test_sets_default_expires_at_48_hours(
        self,
        patched_workflow_db,
    ):
        """Sets expires_at to 48 hours from now by default."""
        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
        )

        created_at = datetime.fromisoformat(workflow["created_at"])
        expires_at = datetime.fromisoformat(workflow["expires_at"])

        assert expires_at - created_at == timedelta(hours=48)

    @pytest.mark.asyncio
    async def test_sets_custom_expires_at(
        self,
        patched_workflow_db,
    ):
        """Sets expires_at to custom hours value."""
        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
            expires_hours=1,
        )

        created_at = datetime.fromisoformat(workflow["created_at"])
        expires_at = datetime.fromisoformat(workflow["expires_at"])

        assert expires_at - created_at == timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_includes_metadata(
        self,
        patched_workflow_db,
    ):
        """Includes metadata in workflow when provided."""
        metadata = {"is_swap": True, "notes": "This is a Robin Hood swap"}

        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.CHORE_VERIFICATION,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
            metadata=metadata,
        )

        assert workflow["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_creates_workflow_with_default_expires(
        self,
        patched_workflow_db,
    ):
        """Creates workflow with default 48 hour expiration."""
        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
        )

        assert "created_at" in workflow
        assert "expires_at" in workflow


class TestGetWorkflow:
    """Test retrieving workflows."""

    @pytest.mark.asyncio
    async def test_returns_workflow_by_id(
        self,
        patched_workflow_db,
    ):
        """Returns workflow when valid ID is provided."""
        created = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
        )

        workflow = await workflow_service.get_workflow(workflow_id=created["id"])

        assert workflow is not None
        assert workflow["id"] == created["id"]
        assert workflow["type"] == "deletion_approval"

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_id(
        self,
        patched_workflow_db,
    ):
        """Returns None when workflow ID doesn't exist."""
        workflow = await workflow_service.get_workflow(workflow_id="nonexistent_id")

        assert workflow is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_id(
        self,
        patched_workflow_db,
    ):
        """Returns None when empty string is provided as ID."""
        workflow = await workflow_service.get_workflow(workflow_id="")

        assert workflow is None


class TestGetPendingWorkflows:
    """Test retrieving pending workflows."""

    @pytest.mark.asyncio
    async def test_returns_all_pending_workflows(
        self,
        patched_workflow_db,
    ):
        """Returns all pending workflows regardless of type."""
        await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user1",
            requester_name="Alice",
            target_id="chore1",
            target_title="Dishes",
        )
        await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.CHORE_VERIFICATION,
            requester_user_id="user2",
            requester_name="Bob",
            target_id="chore2",
            target_title="Trash",
        )
        await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.PERSONAL_VERIFICATION,
            requester_user_id="user3",
            requester_name="Charlie",
            target_id="personal1",
            target_title="Groceries",
        )

        pending = await workflow_service.get_pending_workflows()

        assert len(pending) == 3

    @pytest.mark.asyncio
    async def test_filters_by_workflow_type(
        self,
        patched_workflow_db,
    ):
        """Filters workflows by type when specified."""
        await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user1",
            requester_name="Alice",
            target_id="chore1",
            target_title="Dishes",
        )
        await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.CHORE_VERIFICATION,
            requester_user_id="user2",
            requester_name="Bob",
            target_id="chore2",
            target_title="Trash",
        )

        pending_deletions = await workflow_service.get_pending_workflows(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
        )
        pending_verifications = await workflow_service.get_pending_workflows(
            workflow_type=workflow_service.WorkflowType.CHORE_VERIFICATION,
        )

        assert len(pending_deletions) == 1
        assert pending_deletions[0]["type"] == "deletion_approval"
        assert len(pending_verifications) == 1
        assert pending_verifications[0]["type"] == "chore_verification"

    @pytest.mark.asyncio
    async def test_excludes_non_pending_workflows(
        self,
        patched_workflow_db,
    ):
        """Excludes workflows that are not in pending status."""
        pending_workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user1",
            requester_name="Alice",
            target_id="chore1",
            target_title="Dishes",
        )

        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=pending_workflow["id"],
            data={"status": "approved"},
        )

        pending = await workflow_service.get_pending_workflows()

        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_pending(
        self,
        patched_workflow_db,
    ):
        """Returns empty list when no pending workflows exist."""
        pending = await workflow_service.get_pending_workflows()

        assert pending == []

    @pytest.mark.asyncio
    async def test_create_workflow_then_get_pending_workflows(
        self,
        patched_workflow_db,
    ):
        """Example from acceptance criteria: create workflow, get_pending_workflows returns it."""
        created = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
        )

        pending = await workflow_service.get_pending_workflows()

        assert len(pending) == 1
        assert pending[0]["id"] == created["id"]
        assert pending[0]["type"] == "deletion_approval"

    @pytest.mark.asyncio
    async def test_expires_hours_1_sets_expires_at_correctly(
        self,
        patched_workflow_db,
    ):
        """Example from acceptance criteria: create workflow with expires_hours=1, expires_at is 1 hour from now."""
        workflow = await workflow_service.create_workflow(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
            requester_user_id="user123",
            requester_name="Alice",
            target_id="chore456",
            target_title="Wash Dishes",
            expires_hours=1,
        )

        created_at = datetime.fromisoformat(workflow["created_at"])
        expires_at = datetime.fromisoformat(workflow["expires_at"])

        assert expires_at - created_at == timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_get_workflow_invalid_id_returns_none(
        self,
        patched_workflow_db,
    ):
        """Negative case from acceptance criteria: get_workflow with invalid ID returns None."""
        workflow = await workflow_service.get_workflow(workflow_id="invalid_id_12345")

        assert workflow is None
