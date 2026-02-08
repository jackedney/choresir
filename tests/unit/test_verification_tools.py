"""Unit tests for verification_tools module."""

from typing import TYPE_CHECKING, Any, cast

import pytest

from src.agents.tools.verification_tools import (
    VerifyChore,
    _fuzzy_match_all_chores,
    _fuzzy_match_chore,
    tool_verify_chore,
)
from src.services import chore_service, verification_service, workflow_service


if TYPE_CHECKING:
    from pydantic_ai import RunContext

    from src.agents.base import Deps


@pytest.fixture
def patched_verification_tools_db(monkeypatch, in_memory_db):
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
async def claimer(patched_verification_tools_db):
    """Create a test user who claims chore completion."""
    return await patched_verification_tools_db.create_record(
        collection="members",
        data={
            "phone": "+1234567890",
            "name": "Claimer",
            "role": "member",
            "status": "active",
        },
    )


@pytest.fixture
async def verifier(patched_verification_tools_db):
    """Create a test user who verifies chore completion."""
    return await patched_verification_tools_db.create_record(
        collection="members",
        data={
            "phone": "+1987654321",
            "name": "Verifier",
            "role": "member",
            "status": "active",
        },
    )


@pytest.fixture
async def todo_chore(patched_verification_tools_db, claimer):
    """Create a chore in TODO state."""
    return await chore_service.create_chore(
        title="Test Chore",
        description="Test chore",
        recurrence="0 10 * * *",
        assigned_to=claimer["id"],
    )


@pytest.fixture
async def pending_verification_workflow(patched_verification_tools_db, claimer, todo_chore):
    """Create a pending verification workflow for the chore."""
    return await verification_service.request_verification(
        chore_id=todo_chore["id"],
        claimer_user_id=claimer["id"],
        notes="Just finished it!",
        is_swap=False,
    )


def _create_mock_context(verifier: dict[str, Any]) -> "RunContext[Deps]":
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

    return cast("RunContext[Deps]", MockContext(verifier))


@pytest.mark.unit
class TestToolVerifyChoreByWorkflowId:
    """Tests for tool_verify_chore using workflow_id."""

    async def test_approve_verification_by_workflow_id_success(
        self, patched_verification_tools_db, verifier, pending_verification_workflow
    ):
        """Example from AC: verify chore by workflow_id works."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                workflow_id=pending_verification_workflow["id"],
                decision="APPROVE",
            ),
        )

        # Verify success message
        assert "Approved verification of 'Test Chore'" in result

        # Verify workflow was resolved
        updated_workflow = await workflow_service.get_workflow(workflow_id=pending_verification_workflow["id"])
        assert updated_workflow is not None
        assert updated_workflow["status"] == workflow_service.WorkflowStatus.APPROVED.value
        assert updated_workflow["resolver_user_id"] == verifier["id"]

    async def test_reject_verification_by_workflow_id_success(
        self, patched_verification_tools_db, verifier, pending_verification_workflow
    ):
        """Test rejecting verification by workflow_id works."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                workflow_id=pending_verification_workflow["id"],
                decision="REJECT",
                reason="Not properly done",
            ),
        )

        assert "Rejected verification of 'Test Chore'" in result
        assert "Moving to conflict resolution" in result

        # Verify workflow was rejected
        updated_workflow = await workflow_service.get_workflow(workflow_id=pending_verification_workflow["id"])
        assert updated_workflow is not None
        assert updated_workflow["status"] == workflow_service.WorkflowStatus.REJECTED.value
        assert updated_workflow["reason"] == "Not properly done"

    async def test_workflow_id_not_found(self, patched_verification_tools_db, verifier):
        """Test invalid workflow_id returns error."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                workflow_id="invalid_workflow_id",
                decision="APPROVE",
            ),
        )

        assert "Workflow 'invalid_workflow_id' not found" in result

    async def test_workflow_id_wrong_type(self, patched_verification_tools_db, verifier, claimer):
        """Test workflow_id with wrong type returns error."""
        # Create a deletion workflow instead of verification
        await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=claimer["id"],
                requester_name=claimer["name"],
                target_id="chore_id",
                target_title="Test Chore",
            )
        )

        ctx = _create_mock_context(verifier)

        # Get the workflow we just created
        workflows = await workflow_service.get_pending_workflows(
            workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL
        )
        assert len(workflows) > 0

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                workflow_id=workflows[0]["id"],
                decision="APPROVE",
            ),
        )

        assert "is not a chore verification workflow" in result

    async def test_workflow_id_not_pending(self, patched_verification_tools_db, verifier, claimer, todo_chore):
        """Test workflow_id with not pending status returns error."""
        # Create and approve a workflow
        workflow = await verification_service.request_verification(
            chore_id=todo_chore["id"],
            claimer_user_id=claimer["id"],
        )

        # Approve it using the service directly
        await workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=verifier["id"],
            resolver_name=verifier["name"],
            decision=workflow_service.WorkflowStatus.APPROVED,
        )

        # Now try to verify the already-resolved workflow
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                workflow_id=workflow["id"],
                decision="APPROVE",
            ),
        )

        assert "is not pending" in result


@pytest.mark.unit
class TestToolVerifyChoreByTitle:
    """Tests for tool_verify_chore using chore title matching."""

    async def test_approve_verification_by_title_matching(
        self, patched_verification_tools_db, verifier, pending_verification_workflow
    ):
        """Test approving verification by title matching works."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                chore_title_fuzzy="Test Chore",
                decision="APPROVE",
            ),
        )

        assert "Approved verification of 'Test Chore'" in result

        # Verify workflow was resolved
        updated_workflow = await workflow_service.get_workflow(workflow_id=pending_verification_workflow["id"])
        assert updated_workflow is not None
        assert updated_workflow["status"] == workflow_service.WorkflowStatus.APPROVED.value

    async def test_reject_verification_by_title_matching(
        self, patched_verification_tools_db, verifier, pending_verification_workflow
    ):
        """Test rejecting verification by title matching works."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                chore_title_fuzzy="Test Chore",
                decision="REJECT",
                reason="Not properly done",
            ),
        )

        assert "Rejected verification of 'Test Chore'" in result

    async def test_no_matching_chore_returns_error(self, patched_verification_tools_db, verifier):
        """Test no matching chore returns error message."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                chore_title_fuzzy="Non-existent Chore",
                decision="APPROVE",
            ),
        )

        assert 'No chore found matching "Non-existent Chore"' in result

    async def test_no_pending_verification_returns_error(self, patched_verification_tools_db, verifier, todo_chore):
        """Example from AC: no pending verification returns error message."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                chore_title_fuzzy="Test Chore",
                decision="APPROVE",
            ),
        )

        assert 'No pending verification found for "Test Chore"' in result


@pytest.mark.unit
class TestToolVerifyChoreErrorCases:
    """Tests for error cases in tool_verify_chore."""

    async def test_missing_both_parameters(self, patched_verification_tools_db, verifier):
        """Test missing both workflow_id and chore_title_fuzzy returns error."""
        ctx = _create_mock_context(verifier)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                decision="APPROVE",
            ),
        )

        assert "Either workflow_id or chore_title_fuzzy must be provided" in result

    async def test_self_verification_fails(self, patched_verification_tools_db, claimer, pending_verification_workflow):
        """Test self-verification fails."""
        ctx = _create_mock_context(claimer)

        result = await tool_verify_chore(
            ctx=ctx,
            params=VerifyChore(
                workflow_id=pending_verification_workflow["id"],
                decision="APPROVE",
            ),
        )

        assert "Cannot approve own workflow" in result


@pytest.mark.unit
class TestFuzzyMatchChore:
    """Tests for fuzzy matching functions."""

    def test_exact_match(self):
        """Test exact chore title match."""
        chores = [
            {"id": "1", "title": "Clean Kitchen"},
            {"id": "2", "title": "Take Out Trash"},
        ]

        result = _fuzzy_match_chore(chores, "Clean Kitchen")
        assert result is not None
        assert result["id"] == "1"

    def test_case_insensitive_match(self):
        """Test case-insensitive matching."""
        chores = [{"id": "1", "title": "Clean Kitchen"}]

        result = _fuzzy_match_chore(chores, "clean kitchen")
        assert result is not None

    def test_contains_match(self):
        """Test partial string matching."""
        chores = [
            {"id": "1", "title": "Clean Kitchen"},
            {"id": "2", "title": "Take Out Trash"},
        ]

        result = _fuzzy_match_chore(chores, "Kitchen")
        assert result is not None
        assert result["id"] == "1"

    def test_partial_word_match(self):
        """Test matching by partial words."""
        chores = [
            {"id": "1", "title": "Take Out Trash"},
            {"id": "2", "title": "Clean Kitchen"},
        ]

        result = _fuzzy_match_chore(chores, "Trash")
        assert result is not None
        assert result["id"] == "1"

    def test_no_match_returns_none(self):
        """Test no matching chore returns None."""
        chores = [
            {"id": "1", "title": "Clean Kitchen"},
            {"id": "2", "title": "Take Out Trash"},
        ]

        result = _fuzzy_match_chore(chores, "Do Laundry")
        assert result is None

    def test_fuzzy_match_all_returns_multiple_matches(self):
        """Test fuzzy matching returns all matching chores."""
        chores = [
            {"id": "1", "title": "Clean Kitchen"},
            {"id": "2", "title": "Clean Bathroom"},
            {"id": "3", "title": "Take Out Trash"},
        ]

        results = _fuzzy_match_all_chores(chores, "Clean")
        assert len(results) == 2
        assert any(c["id"] == "1" for c in results)
        assert any(c["id"] == "2" for c in results)
