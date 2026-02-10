"""Unit tests for robin_hood_service module."""

from datetime import UTC, datetime, timedelta

import pytest

import src.modules.tasks.robin_hood as robin_hood_service
from src.core.config import settings


@pytest.fixture
def mock_user_id():
    """Sample user ID for testing."""
    return "test_user_123"


class TestWeekStartDate:
    """Tests for get_week_start_date function."""

    def test_get_week_start_date_monday(self):
        """Test that Monday returns Monday 00:00."""
        monday = datetime(2026, 1, 19, 14, 30, 0, tzinfo=UTC)  # Monday afternoon
        result = robin_hood_service.get_week_start_date(monday)
        expected = datetime(2026, 1, 19, 0, 0, 0, tzinfo=UTC)
        assert result == expected

    def test_get_week_start_date_tuesday(self):
        """Test that Tuesday returns previous Monday 00:00."""
        tuesday = datetime(2026, 1, 20, 10, 0, 0, tzinfo=UTC)  # Tuesday morning
        result = robin_hood_service.get_week_start_date(tuesday)
        expected = datetime(2026, 1, 19, 0, 0, 0, tzinfo=UTC)  # Previous Monday
        assert result == expected

    def test_get_week_start_date_sunday(self):
        """Test that Sunday returns previous Monday 00:00."""
        sunday = datetime(2026, 1, 25, 20, 0, 0, tzinfo=UTC)  # Sunday evening
        result = robin_hood_service.get_week_start_date(sunday)
        expected = datetime(2026, 1, 19, 0, 0, 0, tzinfo=UTC)  # Previous Monday
        assert result == expected

    def test_get_week_start_date_none_uses_current_time(self):
        """Test that None uses current time."""
        result = robin_hood_service.get_week_start_date(None)
        # Should be a Monday 00:00 in the past week
        assert result.weekday() == 0  # Monday
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0


@pytest.mark.asyncio
class TestWeeklyTakeoverCount:
    """Tests for weekly takeover count management."""

    async def test_get_weekly_takeover_count_no_records(self, patched_db, mock_user_id):
        """Test getting count when no records exist."""
        count = await robin_hood_service.get_weekly_takeover_count(mock_user_id)
        assert count == 0

    async def test_get_weekly_takeover_count_with_record(self, patched_db, mock_user_id):
        """Test getting count when record exists."""
        week_start = robin_hood_service.get_week_start_date()

        # Create a record with count of 2
        await patched_db.create_record(
            collection="robin_hood_swaps",
            data={
                "user_id": mock_user_id,
                "week_start_date": week_start.isoformat(),
                "takeover_count": 2,
            },
        )

        count = await robin_hood_service.get_weekly_takeover_count(mock_user_id)
        assert count == 2

    async def test_increment_weekly_takeover_count_new_record(self, patched_db, mock_user_id):
        """Test incrementing creates new record when none exists."""
        count = await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        assert count == 1

        # Verify record was created
        retrieved_count = await robin_hood_service.get_weekly_takeover_count(mock_user_id)
        assert retrieved_count == 1

    async def test_increment_weekly_takeover_count_existing_record(self, patched_db, mock_user_id):
        """Test incrementing updates existing record."""
        week_start = robin_hood_service.get_week_start_date()

        # Create initial record
        await patched_db.create_record(
            collection="robin_hood_swaps",
            data={
                "user_id": mock_user_id,
                "week_start_date": week_start.isoformat(),
                "takeover_count": 1,
            },
        )

        # Increment
        count = await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        assert count == 2

        # Verify
        retrieved_count = await robin_hood_service.get_weekly_takeover_count(mock_user_id)
        assert retrieved_count == 2

    async def test_increment_weekly_takeover_count_multiple_times(self, patched_db, mock_user_id):
        """Test multiple increments."""
        count1 = await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        assert count1 == 1

        count2 = await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        assert count2 == 2

        count3 = await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        assert count3 == 3

    async def test_can_perform_takeover_under_limit(self, patched_db, mock_user_id):
        """Test that takeover is allowed when under limit."""
        # No records yet
        can_takeover, error = await robin_hood_service.can_perform_takeover(mock_user_id)
        assert can_takeover is True
        assert error is None

        # After 1 takeover
        await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        can_takeover, error = await robin_hood_service.can_perform_takeover(mock_user_id)
        assert can_takeover is True
        assert error is None

        # After 2 takeovers
        await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        can_takeover, error = await robin_hood_service.can_perform_takeover(mock_user_id)
        assert can_takeover is True
        assert error is None

    async def test_can_perform_takeover_at_limit(self, patched_db, mock_user_id):
        """Test that takeover is blocked when at limit."""
        # Reach the limit (default is 3)
        await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        await robin_hood_service.increment_weekly_takeover_count(mock_user_id)
        await robin_hood_service.increment_weekly_takeover_count(mock_user_id)

        # Should be blocked
        can_takeover, error = await robin_hood_service.can_perform_takeover(mock_user_id)
        assert can_takeover is False
        assert error is not None
        assert "weekly takeover limit" in error.lower()
        assert str(settings.robin_hood_weekly_limit) in error

    async def test_weekly_reset(self, patched_db, mock_user_id):
        """Test that counts are per week (different weeks have different counts)."""
        # Current week
        current_week_start = robin_hood_service.get_week_start_date()
        await patched_db.create_record(
            collection="robin_hood_swaps",
            data={
                "user_id": mock_user_id,
                "week_start_date": current_week_start.isoformat(),
                "takeover_count": 3,
            },
        )

        # Previous week
        previous_week_start = current_week_start - timedelta(days=7)
        await patched_db.create_record(
            collection="robin_hood_swaps",
            data={
                "user_id": mock_user_id,
                "week_start_date": previous_week_start.isoformat(),
                "takeover_count": 2,
            },
        )

        # Current week should show 3
        count = await robin_hood_service.get_weekly_takeover_count(mock_user_id)
        assert count == 3

        # Should be at limit for current week
        can_takeover, _ = await robin_hood_service.can_perform_takeover(mock_user_id)
        assert can_takeover is False
