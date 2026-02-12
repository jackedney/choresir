"""Unit tests for workflow_service module."""

from datetime import datetime, timedelta
from typing import Any

import pytest

from src.core.db_client import create_record
from src.services import workflow_service
from tests.unit.conftest import DatabaseClient


@pytest.fixture
def patched_workflow_db(mock_db_module_for_unit_tests: Any, db_client: DatabaseClient) -> DatabaseClient:
    """Patches settings and database for workflow service tests.

    Uses real SQLite database via db_client fixture from tests/conftest.py.
    Settings are patched by mock_db_module_for_unit_tests fixture.
    """
    return DatabaseClient()


@pytest.fixture
async def workflow_test_users(patched_workflow_db: DatabaseClient) -> dict[str, dict[str, Any]]:
    """Create real member records for workflow tests and return a mapping of logical names to user records."""
    members = {
        "alice": {"phone": "+15550000001", "name": "Alice", "role": "member", "status": "active"},
        "bob": {"phone": "+15550000002", "name": "Bob", "role": "member", "status": "active"},
        "charlie": {"phone": "+15550000003", "name": "Charlie", "role": "member", "status": "active"},
        "user1": {"phone": "+15550000004", "name": "User1", "role": "member", "status": "active"},
        "user2": {"phone": "+15550000005", "name": "User2", "role": "member", "status": "active"},
        "user3": {"phone": "+15550000006", "name": "User3", "role": "member", "status": "active"},
        "jack": {"phone": "+15550000007", "name": "Jack", "role": "member", "status": "active"},
        "lottie": {"phone": "+15550000008", "name": "Lottie", "role": "member", "status": "active"},
        "other": {"phone": "+15550000009", "name": "Other", "role": "member", "status": "active"},
    }

    created = {}
    for key, data in members.items():
        created[key] = await create_record(collection="members", data=data)

    return created


class TestCreateWorkflow:
    """Test creating workflows."""

    @pytest.mark.asyncio
    async def test_creates_deletion_approval_workflow(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Creates a deletion approval workflow."""
        alice_id = str(workflow_test_users["alice"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        assert workflow["type"] == "deletion_approval"
        assert workflow["status"] == "pending"
        assert workflow["requester_user_id"] == alice_id
        assert workflow["requester_name"] == "Alice"
        assert workflow["target_id"] == "chore456"
        assert workflow["target_title"] == "Wash Dishes"

    @pytest.mark.asyncio
    async def test_creates_task_verification_workflow(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Creates a task verification workflow."""
        charlie_id = str(workflow_test_users["charlie"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=charlie_id,
                requester_name="Bob",
                target_id="chore999",
                target_title="Take Out Trash",
            )
        )

        assert workflow["type"] == "task_verification"
        assert workflow["status"] == "pending"

    @pytest.mark.asyncio
    async def test_creates_task_verification_workflow_with_personal_target(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Creates a task verification workflow for a personal target."""
        bob_id = str(workflow_test_users["bob"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=bob_id,
                requester_name="Charlie",
                target_id="personal_chore123",
                target_title="Buy groceries",
            )
        )

        assert workflow["type"] == "task_verification"
        assert workflow["status"] == "pending"

    @pytest.mark.asyncio
    async def test_sets_default_expires_at_48_hours(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Sets expires_at to 48 hours from now by default."""
        alice_id = str(workflow_test_users["alice"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        created_at = datetime.fromisoformat(workflow["created_at"])
        expires_at = datetime.fromisoformat(workflow["expires_at"])

        assert expires_at - created_at == timedelta(hours=48)

    @pytest.mark.asyncio
    async def test_sets_custom_expires_at(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Sets expires_at to custom hours value."""
        alice_id = str(workflow_test_users["alice"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
                expires_hours=1,
            )
        )

        created_at = datetime.fromisoformat(workflow["created_at"])
        expires_at = datetime.fromisoformat(workflow["expires_at"])

        assert expires_at - created_at == timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_includes_metadata(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Includes metadata in workflow when provided."""
        alice_id = str(workflow_test_users["alice"]["id"])
        metadata = {"is_swap": True, "notes": "This is a Robin Hood swap"}

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
                metadata=metadata,
            )
        )

        assert workflow["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_creates_workflow_with_default_expires(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Creates workflow with default 48 hour expiration."""
        alice_id = str(workflow_test_users["alice"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        assert "created_at" in workflow
        assert "expires_at" in workflow


class TestGetWorkflow:
    """Test retrieving workflows."""

    @pytest.mark.asyncio
    async def test_returns_workflow_by_id(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Returns workflow when valid ID is provided."""
        alice_id = str(workflow_test_users["alice"]["id"])

        created = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
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
        workflow_test_users,
    ):
        """Returns all pending workflows regardless of type."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])
        user3_id = str(workflow_test_users["user3"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Dishes",
            )
        )
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user2_id,
                requester_name="Bob",
                target_id="chore2",
                target_title="Trash",
            )
        )
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user3_id,
                requester_name="Charlie",
                target_id="personal1",
                target_title="Groceries",
            )
        )

        pending = await workflow_service.get_pending_workflows()

        assert len(pending) == 3

    @pytest.mark.asyncio
    async def test_filters_by_workflow_type(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Filters workflows by type when specified."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Dishes",
            )
        )
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user2_id,
                requester_name="Bob",
                target_id="chore2",
                target_title="Trash",
            )
        )

        pending_deletions = await workflow_service.get_pending_workflows(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
        )
        pending_verifications = await workflow_service.get_pending_workflows(
            workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
        )

        assert len(pending_deletions) == 1
        assert pending_deletions[0]["type"] == "deletion_approval"
        assert len(pending_verifications) == 1
        assert pending_verifications[0]["type"] == "task_verification"

    @pytest.mark.asyncio
    async def test_excludes_non_pending_workflows(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Excludes workflows that are not in pending status."""
        user1_id = str(workflow_test_users["user1"]["id"])

        pending_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Dishes",
            )
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
        workflow_test_users,
    ):
        """Example from acceptance criteria: create workflow, get_pending_workflows returns it."""
        alice_id = str(workflow_test_users["alice"]["id"])

        created = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        pending = await workflow_service.get_pending_workflows()

        assert len(pending) == 1
        assert pending[0]["id"] == created["id"]
        assert pending[0]["type"] == "deletion_approval"

    @pytest.mark.asyncio
    async def test_expires_hours_1_sets_expires_at_correctly(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: create workflow with expires_hours=1, expires_at is 1 hour from now."""
        alice_id = str(workflow_test_users["alice"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
                expires_hours=1,
            )
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


class TestGetUserPendingWorkflows:
    """Test retrieving pending workflows for a specific user."""

    @pytest.mark.asyncio
    async def test_returns_workflows_initiated_by_user(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Returns pending workflows where requester_user_id matches the user."""
        jack_id = str(workflow_test_users["jack"]["id"])
        lottie_id = str(workflow_test_users["lottie"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=jack_id,
                requester_name="Jack",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=jack_id,
                requester_name="Jack",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=lottie_id,
                requester_name="Lottie",
                target_id="chore3",
                target_title="Clean Kitchen",
            )
        )

        jacks_pending = await workflow_service.get_user_pending_workflows(user_id=jack_id)

        assert len(jacks_pending) == 2
        assert all(w["requester_user_id"] == jack_id for w in jacks_pending)

    @pytest.mark.asyncio
    async def test_jack_creates_workflow_jacks_pending_includes_it(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: Jack creates workflow, Jack's get_user_pending_workflows includes it."""
        jack_id = str(workflow_test_users["jack"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=jack_id,
                requester_name="Jack",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )

        jacks_pending = await workflow_service.get_user_pending_workflows(user_id=jack_id)

        assert len(jacks_pending) == 1
        assert jacks_pending[0]["requester_user_id"] == jack_id
        assert jacks_pending[0]["requester_name"] == "Jack"

    @pytest.mark.asyncio
    async def test_excludes_non_pending_workflows_for_user(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Excludes workflows that are not in pending status for the user."""
        alice_id = str(workflow_test_users["alice"]["id"])

        pending_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Dishes",
            )
        )

        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=pending_workflow["id"],
            data={"status": "approved"},
        )

        pending = await workflow_service.get_user_pending_workflows(user_id=alice_id)

        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_pending_for_user(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Negative case: no pending workflows returns empty list."""
        alice_id = str(workflow_test_users["alice"]["id"])
        other_id = str(workflow_test_users["other"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=other_id,
                requester_name="Other",
                target_id="chore1",
                target_title="Dishes",
            )
        )

        pending = await workflow_service.get_user_pending_workflows(user_id=alice_id)

        assert pending == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_new_user(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Returns empty list when user has no workflows."""
        # Use a user that exists but has no workflows
        charlie_id = str(workflow_test_users["charlie"]["id"])

        pending = await workflow_service.get_user_pending_workflows(user_id=charlie_id)

        assert pending == []


class TestGetActionableWorkflows:
    """Test retrieving workflows a user can approve/reject."""

    @pytest.mark.asyncio
    async def test_returns_workflows_not_initiated_by_user(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Returns pending workflows where requester_user_id does not match the user."""
        jack_id = str(workflow_test_users["jack"]["id"])
        lottie_id = str(workflow_test_users["lottie"]["id"])
        bob_id = str(workflow_test_users["bob"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=lottie_id,
                requester_name="Lottie",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=bob_id,
                requester_name="Bob",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=jack_id,
                requester_name="Jack",
                target_id="chore3",
                target_title="Clean Kitchen",
            )
        )

        jacks_actionable = await workflow_service.get_actionable_workflows(user_id=jack_id)

        assert len(jacks_actionable) == 2
        assert all(w["requester_user_id"] != jack_id for w in jacks_actionable)
        assert {w["requester_user_id"] for w in jacks_actionable} == {lottie_id, bob_id}

    @pytest.mark.asyncio
    async def test_jack_creates_workflow_lottie_actionable_includes_it(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: Jack creates workflow, Lottie's get_actionable_workflows includes it."""
        jack_id = str(workflow_test_users["jack"]["id"])
        lottie_id = str(workflow_test_users["lottie"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=jack_id,
                requester_name="Jack",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )

        lotties_actionable = await workflow_service.get_actionable_workflows(user_id=lottie_id)

        assert len(lotties_actionable) == 1
        assert lotties_actionable[0]["requester_user_id"] == jack_id
        assert lotties_actionable[0]["requester_name"] == "Jack"

    @pytest.mark.asyncio
    async def test_jack_creates_workflow_jacks_actionable_excludes_it(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: Jack creates workflow, Jack's get_actionable_workflows excludes it."""
        jack_id = str(workflow_test_users["jack"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=jack_id,
                requester_name="Jack",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )

        jacks_actionable = await workflow_service.get_actionable_workflows(user_id=jack_id)

        assert len(jacks_actionable) == 0

    @pytest.mark.asyncio
    async def test_excludes_non_pending_workflows_from_actionable(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Excludes workflows that are not in pending status."""
        alice_id = str(workflow_test_users["alice"]["id"])
        other_id = str(workflow_test_users["other"]["id"])

        other_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=other_id,
                requester_name="Other",
                target_id="chore1",
                target_title="Dishes",
            )
        )

        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=other_workflow["id"],
            data={"status": "approved"},
        )

        actionable = await workflow_service.get_actionable_workflows(user_id=alice_id)

        assert len(actionable) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_actionable_workflows(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Negative case: no pending workflows returns empty list."""
        alice_id = str(workflow_test_users["alice"]["id"])

        actionable = await workflow_service.get_actionable_workflows(user_id=alice_id)

        assert actionable == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_sole_user(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Returns empty list when only workflows are from the user themselves."""
        alice_id = str(workflow_test_users["alice"]["id"])

        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Dishes",
            )
        )

        actionable = await workflow_service.get_actionable_workflows(user_id=alice_id)

        assert actionable == []


class TestResolveWorkflow:
    """Test resolving workflows."""

    @pytest.mark.asyncio
    async def test_resolves_workflow_as_approved(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: resolve workflow as APPROVED, status becomes APPROVED."""
        alice_id = str(workflow_test_users["alice"]["id"])
        bob_id = str(workflow_test_users["bob"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        resolved = await workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=bob_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert resolved["status"] == "approved"
        assert resolved["resolved_at"] is not None
        assert resolved["resolver_user_id"] == bob_id
        assert resolved["resolver_name"] == "Bob"
        assert resolved["requester_user_id"] == alice_id

    @pytest.mark.asyncio
    async def test_resolves_workflow_as_rejected_with_reason(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Resolves workflow as REJECTED with a reason."""
        alice_id = str(workflow_test_users["alice"]["id"])
        bob_id = str(workflow_test_users["bob"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        resolved = await workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=bob_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.REJECTED,
            reason="Not enough time left",
        )

        assert resolved["status"] == "rejected"
        assert resolved["resolved_at"] is not None
        assert resolved["resolver_user_id"] == bob_id
        assert resolved["resolver_name"] == "Bob"
        assert resolved["reason"] == "Not enough time left"

    @pytest.mark.asyncio
    async def test_raises_value_error_when_resolver_is_requester(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Negative case: requester tries to approve own workflow raises ValueError."""
        alice_id = str(workflow_test_users["alice"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        with pytest.raises(ValueError, match="Cannot approve own workflow"):
            await workflow_service.resolve_workflow(
                workflow_id=workflow["id"],
                resolver_user_id=alice_id,
                resolver_name="Alice",
                decision=workflow_service.WorkflowStatus.APPROVED,
            )

    @pytest.mark.asyncio
    async def test_raises_value_error_when_workflow_not_pending(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Negative case: resolve already-resolved workflow raises ValueError."""
        alice_id = str(workflow_test_users["alice"]["id"])
        bob_id = str(workflow_test_users["bob"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=workflow["id"],
            data={"status": "approved"},
        )

        with pytest.raises(ValueError, match="Cannot resolve workflow with status"):
            await workflow_service.resolve_workflow(
                workflow_id=workflow["id"],
                resolver_user_id=bob_id,
                resolver_name="Bob",
                decision=workflow_service.WorkflowStatus.APPROVED,
            )

    @pytest.mark.asyncio
    async def test_raises_value_error_when_workflow_not_found(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Raises ValueError when workflow ID doesn't exist."""
        bob_id = str(workflow_test_users["bob"]["id"])

        with pytest.raises(ValueError, match="Workflow not found"):
            await workflow_service.resolve_workflow(
                workflow_id="nonexistent_id",
                resolver_user_id=bob_id,
                resolver_name="Bob",
                decision=workflow_service.WorkflowStatus.APPROVED,
            )

    @pytest.mark.asyncio
    async def test_raises_value_error_when_decision_invalid(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Raises ValueError when decision is not APPROVED or REJECTED."""
        alice_id = str(workflow_test_users["alice"]["id"])
        bob_id = str(workflow_test_users["bob"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        with pytest.raises(ValueError, match="Invalid decision"):
            await workflow_service.resolve_workflow(
                workflow_id=workflow["id"],
                resolver_user_id=bob_id,
                resolver_name="Bob",
                decision=workflow_service.WorkflowStatus.PENDING,
            )

    @pytest.mark.asyncio
    async def test_sets_resolved_at_timestamp(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Resolution sets resolved_at timestamp."""
        alice_id = str(workflow_test_users["alice"]["id"])
        bob_id = str(workflow_test_users["bob"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        resolved = await workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=bob_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert resolved["resolved_at"] is not None
        resolved_at = datetime.fromisoformat(resolved["resolved_at"])
        assert (datetime.now() - resolved_at).total_seconds() < 10

    @pytest.mark.asyncio
    async def test_accepts_empty_reason(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Accepts empty string for reason parameter."""
        alice_id = str(workflow_test_users["alice"]["id"])
        bob_id = str(workflow_test_users["bob"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        resolved = await workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=bob_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.APPROVED,
            reason="",
        )

        assert "reason" not in resolved


class TestBatchResolveWorkflows:
    """Test batch resolving workflows."""

    @pytest.mark.asyncio
    async def test_resolves_multiple_workflows(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: batch resolve 3 workflows, all 3 returned as resolved."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        workflow1 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        workflow2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )
        workflow3 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="personal1",
                target_title="Buy groceries",
            )
        )

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[workflow1["id"], workflow2["id"], workflow3["id"]],
            resolver_user_id=user2_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert len(resolved) == 3
        assert all(w["status"] == "approved" for w in resolved)
        assert all(w["resolver_user_id"] == user2_id for w in resolved)

    @pytest.mark.asyncio
    async def test_skips_own_workflow(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: batch resolve includes own workflow, that one skipped, others resolved."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        own_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        other_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user2_id,
                requester_name="Bob",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[own_workflow["id"], other_workflow["id"]],
            resolver_user_id=user1_id,
            resolver_name="Alice",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert len(resolved) == 1
        assert resolved[0]["id"] == other_workflow["id"]
        assert resolved[0]["status"] == "approved"

        own_check = await workflow_service.get_workflow(workflow_id=own_workflow["id"])
        assert own_check is not None
        assert own_check["status"] == "pending"

    @pytest.mark.asyncio
    async def test_skips_non_pending_workflows(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Skips workflows not in PENDING status."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        pending_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        approved_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )

        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=approved_workflow["id"],
            data={"status": "approved"},
        )

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[pending_workflow["id"], approved_workflow["id"]],
            resolver_user_id=user2_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert len(resolved) == 1
        assert resolved[0]["id"] == pending_workflow["id"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_workflow_ids(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Negative case: empty workflow_ids list returns empty list."""
        user1_id = str(workflow_test_users["user1"]["id"])

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[],
            resolver_user_id=user1_id,
            resolver_name="Alice",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert resolved == []

    @pytest.mark.asyncio
    async def test_skips_not_found_workflows(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Skips workflows that don't exist."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[workflow["id"], "nonexistent_id"],
            resolver_user_id=user2_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert len(resolved) == 1
        assert resolved[0]["id"] == workflow["id"]

    @pytest.mark.asyncio
    async def test_resolves_with_rejection_reason(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Resolves workflows as REJECTED with a reason."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        workflow1 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        workflow2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[workflow1["id"], workflow2["id"]],
            resolver_user_id=user2_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.REJECTED,
            reason="Not enough time",
        )

        assert len(resolved) == 2
        assert all(w["status"] == "rejected" for w in resolved)
        assert all(w["reason"] == "Not enough time" for w in resolved)

    @pytest.mark.asyncio
    async def test_raises_value_error_for_invalid_decision(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Raises ValueError when decision is not APPROVED or REJECTED."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )

        with pytest.raises(ValueError, match="Invalid decision"):
            await workflow_service.batch_resolve_workflows(
                workflow_ids=[workflow["id"]],
                resolver_user_id=user2_id,
                resolver_name="Bob",
                decision=workflow_service.WorkflowStatus.PENDING,
            )

    @pytest.mark.asyncio
    async def test_handles_mixed_scenarios(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Handles mixed scenarios: own workflow, non-pending, not found, and valid."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])
        user3_id = str(workflow_test_users["user3"]["id"])

        own_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        pending_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user2_id,
                requester_name="Bob",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )
        approved_workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user3_id,
                requester_name="Charlie",
                target_id="personal1",
                target_title="Buy groceries",
            )
        )

        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=approved_workflow["id"],
            data={"status": "approved"},
        )

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[
                own_workflow["id"],
                pending_workflow["id"],
                approved_workflow["id"],
                "nonexistent_id",
            ],
            resolver_user_id=user1_id,
            resolver_name="Alice",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert len(resolved) == 1
        assert resolved[0]["id"] == pending_workflow["id"]
        assert resolved[0]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_sets_resolved_at_timestamp_for_all(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Sets resolved_at timestamp for all resolved workflows."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])

        workflow1 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        workflow2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )

        resolved = await workflow_service.batch_resolve_workflows(
            workflow_ids=[workflow1["id"], workflow2["id"]],
            resolver_user_id=user2_id,
            resolver_name="Bob",
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        assert all(w["resolved_at"] is not None for w in resolved)
        now = datetime.now()
        for workflow in resolved:
            resolved_at = datetime.fromisoformat(workflow["resolved_at"])
            assert (now - resolved_at).total_seconds() < 10


class TestExpireOldWorkflows:
    """Test expiring old workflows."""

    @pytest.mark.asyncio
    async def test_expires_workflow_with_past_expires_at(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: workflow with expires_at in past gets status EXPIRED."""
        alice_id = str(workflow_test_users["alice"]["id"])

        # Create workflow with expires_at in the past
        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        # Manually set expires_at to the past
        past_time = (datetime.now() - timedelta(hours=49)).isoformat()
        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=workflow["id"],
            data={"expires_at": past_time},
        )

        # Expire old workflows
        count = await workflow_service.expire_old_workflows()

        # Verify one workflow was expired
        assert count == 1

        # Verify workflow status is EXPIRED
        expired_workflow = await workflow_service.get_workflow(workflow_id=workflow["id"])
        assert expired_workflow is not None
        assert expired_workflow["status"] == "expired"

    @pytest.mark.asyncio
    async def test_keeps_workflow_with_future_expires_at(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Example from acceptance criteria: workflow with expires_at in future remains PENDING."""
        alice_id = str(workflow_test_users["alice"]["id"])

        # Create workflow with default expires_at (48 hours in future)
        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        # Expire old workflows
        count = await workflow_service.expire_old_workflows()

        # Verify no workflows were expired
        assert count == 0

        # Verify workflow status is still PENDING
        pending_workflow = await workflow_service.get_workflow(workflow_id=workflow["id"])
        assert pending_workflow is not None
        assert pending_workflow["status"] == "pending"

    @pytest.mark.asyncio
    async def test_does_not_touch_already_resolved_workflow(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Negative case from acceptance criteria: already resolved workflow is not touched."""
        alice_id = str(workflow_test_users["alice"]["id"])

        # Create and approve a workflow
        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        # Set expires_at to the past
        past_time = (datetime.now() - timedelta(hours=49)).isoformat()
        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=workflow["id"],
            data={"expires_at": past_time, "status": "approved"},
        )

        # Expire old workflows
        count = await workflow_service.expire_old_workflows()

        # Verify no workflows were expired
        assert count == 0

        # Verify workflow status is still APPROVED
        approved_workflow = await workflow_service.get_workflow(workflow_id=workflow["id"])
        assert approved_workflow is not None
        assert approved_workflow["status"] == "approved"

    @pytest.mark.asyncio
    async def test_expires_multiple_workflows(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Expires multiple workflows at once."""
        user1_id = str(workflow_test_users["user1"]["id"])
        user2_id = str(workflow_test_users["user2"]["id"])
        user3_id = str(workflow_test_users["user3"]["id"])

        # Create multiple workflows
        workflow1 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=user1_id,
                requester_name="Alice",
                target_id="chore1",
                target_title="Wash Dishes",
            )
        )
        workflow2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user2_id,
                requester_name="Bob",
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )
        workflow3 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=user3_id,
                requester_name="Charlie",
                target_id="personal1",
                target_title="Buy groceries",
            )
        )

        # Set first two to have expired
        past_time = (datetime.now() - timedelta(hours=49)).isoformat()
        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=workflow1["id"],
            data={"expires_at": past_time},
        )
        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=workflow2["id"],
            data={"expires_at": past_time},
        )

        # Expire old workflows
        count = await workflow_service.expire_old_workflows()

        # Verify two workflows were expired
        assert count == 2

        # Verify first two are EXPIRED, third is still PENDING
        w1 = await workflow_service.get_workflow(workflow_id=workflow1["id"])
        w2 = await workflow_service.get_workflow(workflow_id=workflow2["id"])
        w3 = await workflow_service.get_workflow(workflow_id=workflow3["id"])

        assert w1 is not None
        assert w2 is not None
        assert w3 is not None
        assert w1["status"] == "expired"
        assert w2["status"] == "expired"
        assert w3["status"] == "pending"

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_expired_workflows(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Returns zero when there are no expired workflows."""
        alice_id = str(workflow_test_users["alice"]["id"])

        # Create workflow with future expires_at
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        # Expire old workflows
        count = await workflow_service.expire_old_workflows()

        # Verify no workflows were expired
        assert count == 0

    @pytest.mark.asyncio
    async def test_expires_workflow_exactly_at_expiration_time(
        self,
        patched_workflow_db,
        workflow_test_users,
    ):
        """Expires workflows where expires_at is exactly at current time."""
        alice_id = str(workflow_test_users["alice"]["id"])

        # Create workflow
        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=alice_id,
                requester_name="Alice",
                target_id="chore456",
                target_title="Wash Dishes",
            )
        )

        # Set expires_at to slightly in the past so it's deterministically expired
        now = datetime.now()
        await patched_workflow_db.update_record(
            collection="workflows",
            record_id=workflow["id"],
            data={"expires_at": (now - timedelta(seconds=1)).isoformat()},
        )

        # Expire old workflows
        count = await workflow_service.expire_old_workflows()

        # Verify workflow was expired
        assert count == 1
