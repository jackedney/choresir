"""Unit tests for chore_service module."""

import pytest

from src.core.db_client import RecordNotFoundError
from src.domain.chore import ChoreState
from src.services import chore_service


@pytest.fixture
def patched_chore_db(monkeypatch, in_memory_db):
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
class TestCreateChore:
    """Tests for create_chore function."""

    async def test_create_chore_with_cron_success(self, patched_chore_db):
        """Test creating a chore with CRON expression."""
        result = await chore_service.create_chore(
            title="Daily Dishes",
            description="Wash all dishes",
            recurrence="0 20 * * *",  # 8 PM daily
            assigned_to="user123",
        )

        assert result["title"] == "Daily Dishes"
        assert result["description"] == "Wash all dishes"
        assert result["schedule_cron"] == "0 20 * * *"
        assert result["assigned_to"] == "user123"
        assert result["current_state"] == ChoreState.TODO
        assert "deadline" in result
        assert "id" in result

    async def test_create_chore_every_x_days(self, patched_chore_db):
        """Test creating a chore with 'every X days' format."""
        result = await chore_service.create_chore(
            title="Weekly Cleanup",
            description="Clean the house",
            recurrence="every 7 days",
            assigned_to="user456",
        )

        assert result["title"] == "Weekly Cleanup"
        # Should be converted to INTERVAL format
        assert "INTERVAL:7:" in result["schedule_cron"]
        assert result["assigned_to"] == "user456"
        assert result["current_state"] == ChoreState.TODO

    async def test_create_chore_unassigned(self, patched_chore_db):
        """Test creating an unassigned chore."""
        result = await chore_service.create_chore(
            title="Unassigned Task",
            description="To be assigned",
            recurrence="0 10 * * *",
            assigned_to=None,
        )

        assert result["assigned_to"] == ""  # Empty string for unassigned

    async def test_create_chore_invalid_recurrence(self, patched_chore_db):
        """Test creating a chore with invalid recurrence format fails."""
        with pytest.raises(ValueError, match="Invalid recurrence format"):
            await chore_service.create_chore(
                title="Bad Chore",
                description="Test",
                recurrence="invalid format",
                assigned_to="user123",
            )


@pytest.mark.unit
class TestGetChores:
    """Tests for get_chores function."""

    @pytest.fixture
    async def created_chores(self, patched_chore_db):
        """Create multiple chores for testing."""
        chore1 = await chore_service.create_chore(
            title="Chore 1",
            description="First chore",
            recurrence="0 9 * * *",
            assigned_to="user1",
        )

        chore2 = await chore_service.create_chore(
            title="Chore 2",
            description="Second chore",
            recurrence="0 10 * * *",
            assigned_to="user2",
        )

        chore3 = await chore_service.create_chore(
            title="Chore 3",
            description="Third chore",
            recurrence="0 11 * * *",
            assigned_to="user1",
        )

        return [chore1, chore2, chore3]

    async def test_get_all_chores(self, patched_chore_db, created_chores):
        """Test retrieving all chores without filters."""
        result = await chore_service.get_chores()

        assert len(result) == 3
        assert all("id" in chore for chore in result)

    async def test_get_chores_by_user(self, patched_chore_db, created_chores):
        """Test filtering chores by user ID."""
        result = await chore_service.get_chores(user_id="user1")

        assert len(result) == 2
        assert all(chore["assigned_to"] == "user1" for chore in result)

    async def test_get_chores_by_state(self, patched_chore_db, created_chores):
        """Test filtering chores by state."""
        result = await chore_service.get_chores(state=ChoreState.TODO)

        assert len(result) == 3
        assert all(chore["current_state"] == ChoreState.TODO for chore in result)

    async def test_get_chores_empty_result(self, patched_chore_db):
        """Test getting chores when none exist."""
        result = await chore_service.get_chores()

        assert result == []

    async def test_get_chores_nonexistent_user(self, patched_chore_db, created_chores):
        """Test filtering by non-existent user returns empty list."""
        result = await chore_service.get_chores(user_id="nonexistent")

        assert result == []


@pytest.mark.unit
class TestMarkPendingVerification:
    """Tests for mark_pending_verification function."""

    @pytest.fixture
    async def todo_chore(self, patched_chore_db):
        """Create a chore in TODO state."""
        return await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

    async def test_mark_pending_verification_success(self, patched_chore_db, todo_chore):
        """Test transitioning chore to PENDING_VERIFICATION."""
        result = await chore_service.mark_pending_verification(chore_id=todo_chore["id"])

        assert result["id"] == todo_chore["id"]
        assert result["current_state"] == ChoreState.PENDING_VERIFICATION

    async def test_mark_pending_verification_not_found(self, patched_chore_db):
        """Test marking non-existent chore raises error."""
        with pytest.raises(RecordNotFoundError):
            await chore_service.mark_pending_verification(chore_id="nonexistent_id")


@pytest.mark.unit
class TestCompleteChore:
    """Tests for complete_chore function."""

    @pytest.fixture
    async def pending_chore(self, patched_chore_db):
        """Create a chore in PENDING_VERIFICATION state."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        # Transition to pending verification
        return await chore_service.mark_pending_verification(chore_id=chore["id"])

    async def test_complete_chore_success(self, patched_chore_db, pending_chore):
        """Test completing a chore."""
        result = await chore_service.complete_chore(chore_id=pending_chore["id"])

        assert result["id"] == pending_chore["id"]
        assert result["current_state"] == ChoreState.COMPLETED
        # Deadline should be updated to next occurrence
        # (Note: the actual state machine may handle this differently)

    async def test_complete_chore_not_found(self, patched_chore_db):
        """Test completing non-existent chore raises error."""
        with pytest.raises(RecordNotFoundError):
            await chore_service.complete_chore(chore_id="nonexistent_id")


@pytest.mark.unit
class TestMoveToConflict:
    """Tests for move_to_conflict function."""

    @pytest.fixture
    async def pending_chore(self, patched_chore_db):
        """Create a chore in PENDING_VERIFICATION state."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        return await chore_service.mark_pending_verification(chore_id=chore["id"])

    async def test_move_to_conflict_success(self, patched_chore_db, pending_chore):
        """Test transitioning chore to CONFLICT state."""
        result = await chore_service.move_to_conflict(chore_id=pending_chore["id"])

        assert result["id"] == pending_chore["id"]
        assert result["current_state"] == ChoreState.CONFLICT

    async def test_move_to_conflict_not_found(self, patched_chore_db):
        """Test moving non-existent chore to conflict raises error."""
        with pytest.raises(RecordNotFoundError):
            await chore_service.move_to_conflict(chore_id="nonexistent_id")


@pytest.mark.unit
class TestResetChoreToTodo:
    """Tests for reset_chore_to_todo function."""

    @pytest.fixture
    async def conflict_chore(self, patched_chore_db):
        """Create a chore in CONFLICT state."""
        chore = await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )
        # Transition through states to conflict
        pending = await chore_service.mark_pending_verification(chore_id=chore["id"])
        return await chore_service.move_to_conflict(chore_id=pending["id"])

    async def test_reset_chore_to_todo_success(self, patched_chore_db, conflict_chore):
        """Test resetting a chore back to TODO state."""
        result = await chore_service.reset_chore_to_todo(chore_id=conflict_chore["id"])

        assert result["id"] == conflict_chore["id"]
        assert result["current_state"] == ChoreState.TODO

    async def test_reset_chore_to_todo_not_found(self, patched_chore_db):
        """Test resetting non-existent chore raises error."""
        with pytest.raises(RecordNotFoundError):
            await chore_service.reset_chore_to_todo(chore_id="nonexistent_id")


@pytest.mark.unit
class TestGetChoreById:
    """Tests for get_chore_by_id function."""

    @pytest.fixture
    async def test_chore(self, patched_chore_db):
        """Create a test chore."""
        return await chore_service.create_chore(
            title="Test Chore",
            description="Test",
            recurrence="0 10 * * *",
            assigned_to="user1",
        )

    async def test_get_chore_by_id_found(self, patched_chore_db, test_chore):
        """Test retrieving chore by ID when exists."""
        result = await chore_service.get_chore_by_id(chore_id=test_chore["id"])

        assert result["id"] == test_chore["id"]
        assert result["title"] == test_chore["title"]
        assert result["description"] == test_chore["description"]

    async def test_get_chore_by_id_not_found(self, patched_chore_db):
        """Test retrieving non-existent chore raises RecordNotFoundError."""
        with pytest.raises(RecordNotFoundError):
            await chore_service.get_chore_by_id(chore_id="nonexistent_id")


@pytest.mark.unit
class TestRecurrenceParsing:
    """Tests for recurrence parsing logic."""

    async def test_cron_expression_accepted(self, patched_chore_db):
        """Test that valid CRON expressions are accepted."""
        chore = await chore_service.create_chore(
            title="CRON Test",
            description="Test CRON",
            recurrence="*/15 * * * *",  # Every 15 minutes
            assigned_to="user1",
        )

        assert chore["schedule_cron"] == "*/15 * * * *"

    async def test_every_1_day_format(self, patched_chore_db):
        """Test 'every 1 day' format (singular)."""
        chore = await chore_service.create_chore(
            title="Daily Test",
            description="Test",
            recurrence="every 1 day",
            assigned_to="user1",
        )

        assert "INTERVAL:1:" in chore["schedule_cron"]

    async def test_every_30_days_format(self, patched_chore_db):
        """Test 'every 30 days' format."""
        chore = await chore_service.create_chore(
            title="Monthly Test",
            description="Test",
            recurrence="every 30 days",
            assigned_to="user1",
        )

        assert "INTERVAL:30:" in chore["schedule_cron"]

    async def test_invalid_format_raises_error(self, patched_chore_db):
        """Test various invalid recurrence formats."""
        invalid_formats = [
            "every week",
            "daily",
            "monthly",
            "every 5 hours",
            "every",
            "5 days",
        ]

        for invalid_format in invalid_formats:
            with pytest.raises(ValueError, match="Invalid recurrence format"):
                await chore_service.create_chore(
                    title="Invalid Test",
                    description="Test",
                    recurrence=invalid_format,
                    assigned_to="user1",
                )
