"""Unit tests for chore_tools module."""

from typing import TYPE_CHECKING, Any, cast

import pytest

import src.modules.tasks.deletion as deletion_service
import src.modules.tasks.service as chore_service
from src.modules.tasks.tools import (
    BatchRespondToWorkflows,
    RespondToDeletion,
    tool_batch_respond_to_workflows,
    tool_respond_to_deletion,
)
from src.services import workflow_service


if TYPE_CHECKING:
    from pydantic_ai import RunContext

    from src.agents.base import Deps


@pytest.fixture
def patched_chore_tools_db(monkeypatch, in_memory_db):
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
async def requester(patched_chore_tools_db):
    """Create a test user who requests deletion."""
    return await patched_chore_tools_db.create_record(
        collection="members",
        data={
            "phone": "+1234567890",
            "name": "Requester",
            "role": "member",
            "status": "active",
        },
    )


@pytest.fixture
async def resolver(patched_chore_tools_db):
    """Create a test user who approves/deletes."""
    return await patched_chore_tools_db.create_record(
        collection="members",
        data={
            "phone": "+1987654321",
            "name": "Resolver",
            "role": "member",
            "status": "active",
        },
    )


@pytest.fixture
async def todo_chore(patched_chore_tools_db, requester):
    """Create a chore in TODO state."""
    return await chore_service.create_chore(
        title="Test Chore",
        description="Test chore",
        recurrence="0 10 * * *",
        assigned_to=requester["id"],
    )


@pytest.fixture
async def pending_deletion_workflow(patched_chore_tools_db, requester, todo_chore):
    """Create a pending deletion workflow for the chore."""
    return await deletion_service.request_chore_deletion(
        chore_id=todo_chore["id"],
        requester_user_id=requester["id"],
        reason="No longer needed",
    )


def _create_mock_context(resolver: dict[str, Any]) -> "RunContext[Deps]":
    """Create a minimal mock context object for testing."""

    class MockDeps:
        def __init__(self, user_data: dict[str, Any]) -> None:
            self.user_id = user_data["id"]
            self.user_phone = user_data["phone"]
            self.user_name = user_data["name"]
            self.user_role = user_data["role"]
            self.current_time = None

    class MockContext:
        def __init__(self, user_data: dict[str, Any]) -> None:
            self.deps = MockDeps(user_data)

    return cast("RunContext[Deps]", MockContext(resolver))


@pytest.mark.unit
class TestToolRespondToDeletionByWorkflowId:
    """Tests for tool_respond_to_deletion using workflow_id."""

    async def test_approve_deletion_by_workflow_id_success(
        self, patched_chore_tools_db, resolver, pending_deletion_workflow
    ):
        """Test approving deletion by workflow_id works."""
        ctx = _create_mock_context(resolver)

        # Approve deletion by workflow_id
        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                workflow_id=pending_deletion_workflow["id"],
                decision="approve",
            ),
        )

        # Verify success message
        assert "Approved deletion of 'Test Chore'" in result
        assert "chore has been archived" in result

        # Verify workflow was resolved
        updated_workflow = await workflow_service.get_workflow(workflow_id=pending_deletion_workflow["id"])
        assert updated_workflow is not None
        assert updated_workflow["status"] == workflow_service.WorkflowStatus.APPROVED.value
        assert updated_workflow["resolver_user_id"] == resolver["id"]

    async def test_reject_deletion_by_workflow_id_success(
        self, patched_chore_tools_db, resolver, pending_deletion_workflow
    ):
        """Test rejecting deletion by workflow_id works."""
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                workflow_id=pending_deletion_workflow["id"],
                decision="reject",
                reason="Still needed",
            ),
        )

        assert "Rejected deletion request for 'Test Chore'" in result
        assert "chore will remain active" in result

        # Verify workflow was rejected
        updated_workflow = await workflow_service.get_workflow(workflow_id=pending_deletion_workflow["id"])
        assert updated_workflow is not None
        assert updated_workflow["status"] == workflow_service.WorkflowStatus.REJECTED.value
        assert updated_workflow["reason"] == "Still needed"

    async def test_workflow_id_not_found(self, patched_chore_tools_db, resolver):
        """Test invalid workflow_id returns error."""
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                workflow_id="invalid_workflow_id",
                decision="approve",
            ),
        )

        assert "Workflow 'invalid_workflow_id' not found" in result

    async def test_workflow_id_wrong_type(self, patched_chore_tools_db, resolver, requester):
        """Test workflow_id with wrong type returns error."""
        # Create a chore verification workflow instead of deletion
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore_id",
                target_title="Test Chore",
            )
        )

        ctx = _create_mock_context(resolver)

        # Get the workflow we just created
        workflows = await workflow_service.get_pending_workflows(
            workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION
        )
        assert len(workflows) > 0

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                workflow_id=workflows[0]["id"],
                decision="approve",
            ),
        )

        assert "is not a deletion approval workflow" in result

    async def test_workflow_id_not_pending(self, patched_chore_tools_db, resolver, requester, todo_chore):
        """Test workflow_id with not pending status returns error."""
        # Create and approve a workflow
        workflow = await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id=requester["id"],
        )

        # Approve it using the service directly
        await workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=resolver["id"],
            resolver_name=resolver["name"],
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        # Now try to respond to the already-resolved workflow
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                workflow_id=workflow["id"],
                decision="approve",
            ),
        )

        assert "is not pending" in result


@pytest.mark.unit
class TestToolRespondToDeletionByTitle:
    """Tests for tool_respond_to_deletion using chore title matching."""

    async def test_approve_deletion_by_title_matching(
        self, patched_chore_tools_db, resolver, pending_deletion_workflow
    ):
        """Test approving deletion by title matching works."""
        ctx = _create_mock_context(resolver)

        # Approve by title match
        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                chore_title_fuzzy="Test Chore",
                decision="approve",
            ),
        )

        assert "Approved deletion of 'Test Chore'" in result

        # Verify workflow was resolved
        updated_workflow = await workflow_service.get_workflow(workflow_id=pending_deletion_workflow["id"])
        assert updated_workflow is not None
        assert updated_workflow["status"] == workflow_service.WorkflowStatus.APPROVED.value

    async def test_reject_deletion_by_title_matching(self, patched_chore_tools_db, resolver, pending_deletion_workflow):
        """Test rejecting deletion by title matching works."""
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                chore_title_fuzzy="Test Chore",
                decision="reject",
                reason="Still needed",
            ),
        )

        assert "Rejected deletion request for 'Test Chore'" in result

    async def test_no_matching_workflow_returns_error(self, patched_chore_tools_db, resolver):
        """Test no matching workflow returns error message."""
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                chore_title_fuzzy="Non-existent Chore",
                decision="approve",
            ),
        )

        assert 'No chore found matching "Non-existent Chore"' in result


@pytest.mark.unit
class TestToolRespondToDeletionErrorCases:
    """Tests for error cases in tool_respond_to_deletion."""

    async def test_invalid_decision(self, patched_chore_tools_db, resolver):
        """Test invalid decision returns error."""
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                workflow_id="some_id",
                decision="invalid",
            ),
        )

        assert "Invalid decision 'invalid'" in result

    async def test_missing_both_parameters(self, patched_chore_tools_db, resolver):
        """Test missing both workflow_id and chore_title_fuzzy returns error."""
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                decision="approve",
            ),
        )

        assert "Either workflow_id or chore_title_fuzzy must be provided" in result

    async def test_self_approval_fails(self, patched_chore_tools_db, requester, pending_deletion_workflow):
        """Test self-approval fails."""
        ctx = _create_mock_context(requester)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                workflow_id=pending_deletion_workflow["id"],
                decision="approve",
            ),
        )

        assert "Cannot approve own workflow" in result

    async def test_no_pending_workflow_for_chore(self, patched_chore_tools_db, resolver, todo_chore):
        """Test no pending workflow for chore returns error."""
        ctx = _create_mock_context(resolver)

        result = await tool_respond_to_deletion(
            ctx=ctx,
            params=RespondToDeletion(
                chore_title_fuzzy="Test Chore",
                decision="approve",
            ),
        )

        assert "No pending deletion request found" in result


@pytest.mark.unit
class TestToolBatchRespondToWorkflows:
    """Tests for tool_batch_respond_to_workflows."""

    async def test_approve_indices_two_workflows(self, patched_chore_tools_db, requester, resolver, todo_chore):
        """Example from AC: approve indices [1, 2] resolves first two actionable workflows."""
        # Create two deletion workflows from requester
        wf1 = await deletion_service.request_chore_deletion(
            chore_id=todo_chore["id"],
            requester_user_id=requester["id"],
        )
        wf2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )

        ctx = _create_mock_context(resolver)

        # Approve indices 1 and 2
        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                indices=[1, 2],
                decision="approve",
            ),
        )

        assert "Approved 2 workflows" in result
        assert '"Test Chore"' in result
        assert '"Take Out Trash"' in result

        # Verify both workflows were approved
        updated_wf1 = await workflow_service.get_workflow(workflow_id=wf1["id"])
        updated_wf2 = await workflow_service.get_workflow(workflow_id=wf2["id"])
        assert updated_wf1 is not None
        assert updated_wf2 is not None
        assert updated_wf1["status"] == workflow_service.WorkflowStatus.APPROVED.value
        assert updated_wf2["status"] == workflow_service.WorkflowStatus.APPROVED.value

    async def test_reject_indices_two_workflows(self, patched_chore_tools_db, requester, resolver):
        """Test rejecting multiple workflows by indices."""
        wf1 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore1",
                target_title="Clean Kitchen",
            )
        )
        wf2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )

        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                indices=[1, 2],
                decision="reject",
                reason="Too busy",
            ),
        )

        assert "Rejected 2 workflows" in result
        assert '"Clean Kitchen"' in result
        assert '"Take Out Trash"' in result

        # Verify both workflows were rejected with reason
        updated_wf1 = await workflow_service.get_workflow(workflow_id=wf1["id"])
        updated_wf2 = await workflow_service.get_workflow(workflow_id=wf2["id"])
        assert updated_wf1 is not None
        assert updated_wf2 is not None
        assert updated_wf1["status"] == workflow_service.WorkflowStatus.REJECTED.value
        assert updated_wf2["status"] == workflow_service.WorkflowStatus.REJECTED.value
        assert updated_wf1["reason"] == "Too busy"
        assert updated_wf2["reason"] == "Too busy"

    async def test_approve_by_workflow_ids(self, patched_chore_tools_db, requester, resolver):
        """Test approving workflows by direct workflow IDs."""
        wf1 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore1",
                target_title="Clean Kitchen",
            )
        )
        wf2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )

        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                workflow_ids=[wf1["id"], wf2["id"]],
                decision="approve",
            ),
        )

        assert "Approved 2 workflows" in result

    async def test_approve_single_workflow(self, patched_chore_tools_db, requester, resolver):
        """Test approving single workflow returns singular message."""
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore1",
                target_title="Clean Kitchen",
            )
        )

        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                indices=[1],
                decision="approve",
            ),
        )

        assert "Approved 1 workflow" in result
        assert '"Clean Kitchen"' in result

    async def test_no_actionable_workflows_returns_message(self, patched_chore_tools_db, resolver):
        """Negative case: no actionable workflows returns appropriate message."""
        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                indices=[1],
                decision="approve",
            ),
        )

        assert "No actionable workflows found" in result

    async def test_invalid_decision_returns_error(self, patched_chore_tools_db, requester, resolver):
        """Test invalid decision returns error message."""
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore1",
                target_title="Clean Kitchen",
            )
        )

        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                indices=[1],
                decision="invalid",
            ),
        )

        assert "Invalid decision 'invalid'" in result

    async def test_missing_both_parameters_returns_error(self, patched_chore_tools_db, resolver):
        """Test missing both workflow_ids and indices returns error."""
        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                decision="approve",
            ),
        )

        assert "Either workflow_ids or indices must be provided" in result

    async def test_skips_own_workflow(self, patched_chore_tools_db, requester, resolver):
        """Test that own workflow is skipped during batch resolution."""
        # Create workflow from resolver (should be skipped)
        own_wf = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=resolver["id"],
                requester_name=resolver["name"],
                target_id="chore1",
                target_title="Own Workflow",
            )
        )
        # Create workflow from requester (should be resolved)
        other_wf = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore2",
                target_title="Other Workflow",
            )
        )

        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                workflow_ids=[own_wf["id"], other_wf["id"]],
                decision="approve",
            ),
        )

        # Should only resolve one workflow (skips own)
        assert "Approved 1 workflow" in result
        assert '"Other Workflow"' in result

        # Verify own workflow is still pending
        own_check = await workflow_service.get_workflow(workflow_id=own_wf["id"])
        assert own_check is not None
        assert own_check["status"] == workflow_service.WorkflowStatus.PENDING.value
        # Verify other workflow is approved
        other_check = await workflow_service.get_workflow(workflow_id=other_wf["id"])
        assert other_check is not None
        assert other_check["status"] == workflow_service.WorkflowStatus.APPROVED.value

    async def test_out_of_range_index_is_skipped(self, patched_chore_tools_db, requester, resolver):
        """Test that out of range indices are skipped."""
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore1",
                target_title="Clean Kitchen",
            )
        )

        ctx = _create_mock_context(resolver)

        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                indices=[1, 2, 3],  # Only index 1 is valid
                decision="approve",
            ),
        )

        assert "Approved 1 workflow" in result
        assert '"Clean Kitchen"' in result

    async def test_approve_all_workflows(self, patched_chore_tools_db, requester, resolver):
        """Example from AC: approve 'all' resolves all actionable workflows."""
        wf1 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore1",
                target_title="Clean Kitchen",
            )
        )
        wf2 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="chore2",
                target_title="Take Out Trash",
            )
        )
        wf3 = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=requester["id"],
                requester_name=requester["name"],
                target_id="personal1",
                target_title="Buy groceries",
            )
        )

        ctx = _create_mock_context(resolver)

        # Use indices=[0] to approve all actionable workflows
        result = await tool_batch_respond_to_workflows(
            ctx=ctx,
            params=BatchRespondToWorkflows(
                indices=[0],  # Special index 0 means "all"
                decision="approve",
            ),
        )

        assert "Approved 3 workflows" in result

        # Verify all three workflows were approved
        updated_wf1 = await workflow_service.get_workflow(workflow_id=wf1["id"])
        updated_wf2 = await workflow_service.get_workflow(workflow_id=wf2["id"])
        updated_wf3 = await workflow_service.get_workflow(workflow_id=wf3["id"])
        assert updated_wf1 is not None
        assert updated_wf2 is not None
        assert updated_wf3 is not None
        assert all(
            wf["status"] == workflow_service.WorkflowStatus.APPROVED.value
            for wf in [updated_wf1, updated_wf2, updated_wf3]
        )
