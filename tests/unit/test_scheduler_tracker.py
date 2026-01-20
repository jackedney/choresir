"""Tests for scheduler job tracking and retry functionality."""

from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from src.core.scheduler_tracker import JobTracker, retry_job_with_backoff


@pytest.fixture(autouse=True)
def mock_redis_unavailable():
    """Mock redis_client to be unavailable, forcing in-memory storage for all tests."""
    with patch("src.core.scheduler_tracker.redis_client") as mock_redis:
        type(mock_redis).is_available = PropertyMock(return_value=False)
        yield mock_redis


@pytest.fixture
def job_tracker() -> JobTracker:
    """Create a job tracker instance for testing with in-memory storage."""
    return JobTracker()


@pytest.mark.unit
async def test_record_job_start_in_memory(job_tracker: JobTracker) -> None:
    """Test recording job start in memory storage."""
    await job_tracker.record_job_start("test_job")

    status = await job_tracker.get_job_status("test_job")
    assert status["currently_running"] is True
    assert status["current_run_started"] is not None


@pytest.mark.unit
async def test_record_job_success_in_memory(job_tracker: JobTracker) -> None:
    """Test recording successful job execution in memory."""
    await job_tracker.record_job_start("test_job")
    await job_tracker.record_job_success("test_job")

    status = await job_tracker.get_job_status("test_job")
    assert status["last_success"] is not None
    assert status["consecutive_failures"] == 0
    assert status["success_count"] == 1
    assert status["currently_running"] is False


@pytest.mark.unit
async def test_record_job_failure_in_memory(job_tracker: JobTracker) -> None:
    """Test recording failed job execution in memory."""
    await job_tracker.record_job_start("test_job")
    await job_tracker.record_job_failure("test_job", "Test error")

    status = await job_tracker.get_job_status("test_job")
    assert status["last_failure"] is not None
    assert status["last_error"] == "Test error"
    assert status["consecutive_failures"] == 1
    assert status["failure_count"] == 1
    assert status["currently_running"] is False


@pytest.mark.unit
async def test_consecutive_failures_tracking(job_tracker: JobTracker) -> None:
    """Test that consecutive failures are tracked correctly."""
    # First failure
    await job_tracker.record_job_start("test_job")
    await job_tracker.record_job_failure("test_job", "Error 1")
    status = await job_tracker.get_job_status("test_job")
    assert status["consecutive_failures"] == 1

    # Second failure
    await job_tracker.record_job_start("test_job")
    await job_tracker.record_job_failure("test_job", "Error 2")
    status = await job_tracker.get_job_status("test_job")
    assert status["consecutive_failures"] == 2

    # Success should reset consecutive failures
    await job_tracker.record_job_start("test_job")
    await job_tracker.record_job_success("test_job")
    status = await job_tracker.get_job_status("test_job")
    assert status["consecutive_failures"] == 0
    assert status["failure_count"] == 2  # Total failures still tracked


@pytest.mark.unit
async def test_add_to_dead_letter_queue(job_tracker: JobTracker) -> None:
    """Test adding job to dead letter queue."""
    await job_tracker.add_to_dead_letter_queue("failed_job", "Persistent error", "Failed 3 consecutive times")

    dlq = job_tracker.get_dead_letter_queue()
    assert len(dlq) == 1
    assert dlq[0]["job_name"] == "failed_job"
    assert dlq[0]["error"] == "Persistent error"
    assert dlq[0]["context"] == "Failed 3 consecutive times"


@pytest.mark.unit
async def test_dead_letter_queue_max_size(job_tracker: JobTracker) -> None:
    """Test that dead letter queue respects max size limit."""
    # Add more than max size (100)
    for i in range(150):
        await job_tracker.add_to_dead_letter_queue(f"job_{i}", f"error_{i}", "context")

    dlq = job_tracker.get_dead_letter_queue()
    assert len(dlq) == 100  # Should only keep last 100


@pytest.mark.unit
async def test_retry_job_with_backoff_success_first_try() -> None:
    """Test successful job execution on first try."""
    mock_job = AsyncMock()

    with patch("src.core.scheduler_tracker.job_tracker") as mock_tracker:
        mock_tracker.record_job_start = AsyncMock()
        mock_tracker.record_job_success = AsyncMock()

        await retry_job_with_backoff(mock_job, "test_job")

        # Job should be called once
        mock_job.assert_called_once()

        # Should record start and success
        mock_tracker.record_job_start.assert_called_once_with("test_job")
        mock_tracker.record_job_success.assert_called_once_with("test_job")


@pytest.mark.unit
async def test_retry_job_with_backoff_success_after_retry() -> None:
    """Test successful job execution after retries."""
    mock_job = AsyncMock(side_effect=[Exception("Error 1"), Exception("Error 2"), None])

    with patch("src.core.scheduler_tracker.job_tracker") as mock_tracker:
        mock_tracker.record_job_start = AsyncMock()
        mock_tracker.record_job_success = AsyncMock()

        await retry_job_with_backoff(mock_job, "test_job", max_retries=3)

        # Job should be called 3 times (2 failures + 1 success)
        assert mock_job.call_count == 3

        # Should record success after retries
        mock_tracker.record_job_success.assert_called_once_with("test_job")


@pytest.mark.unit
async def test_retry_job_with_backoff_all_retries_exhausted() -> None:
    """Test job failure after all retries exhausted."""
    mock_job = AsyncMock(side_effect=Exception("Persistent error"))

    with (
        patch("src.core.scheduler_tracker.job_tracker") as mock_tracker,
        patch("src.core.scheduler_tracker.notify_admins") as mock_notify,
    ):
        mock_tracker.record_job_start = AsyncMock()
        mock_tracker.record_job_failure = AsyncMock(return_value=1)
        mock_tracker.add_to_dead_letter_queue = AsyncMock()
        mock_notify.return_value = None

        await retry_job_with_backoff(mock_job, "test_job", max_retries=3)

        # Job should be called max_retries times
        assert mock_job.call_count == 3

        # Should record failure
        mock_tracker.record_job_failure.assert_called_once()

        # Should notify admins
        mock_notify.assert_called()


@pytest.mark.unit
async def test_retry_job_with_backoff_adds_to_dlq_after_consecutive_failures() -> None:
    """Test that job is added to DLQ after 3+ consecutive failures."""
    mock_job = AsyncMock(side_effect=Exception("Persistent error"))

    with (
        patch("src.core.scheduler_tracker.job_tracker") as mock_tracker,
        patch("src.core.scheduler_tracker.notify_admins") as mock_notify,
    ):
        mock_tracker.record_job_start = AsyncMock()
        mock_tracker.record_job_failure = AsyncMock(return_value=3)  # 3 consecutive failures
        mock_tracker.add_to_dead_letter_queue = AsyncMock()
        mock_notify.return_value = None

        await retry_job_with_backoff(mock_job, "test_job", max_retries=2)

        # Should add to dead letter queue
        mock_tracker.add_to_dead_letter_queue.assert_called_once()

        # Should notify admins twice (once for failure, once for DLQ)
        assert mock_notify.call_count == 2


@pytest.mark.unit
async def test_get_job_status_for_nonexistent_job(job_tracker: JobTracker) -> None:
    """Test getting status for a job that hasn't run yet."""
    status = await job_tracker.get_job_status("nonexistent_job")

    assert status["job_name"] == "nonexistent_job"
    assert status["last_success"] is None
    assert status["last_failure"] is None
    assert status["consecutive_failures"] == 0
    assert status["success_count"] == 0
    assert status["failure_count"] == 0
    assert status["currently_running"] is False


@pytest.mark.unit
async def test_error_truncation(job_tracker: JobTracker) -> None:
    """Test that long error messages are truncated."""
    long_error = "x" * 1000  # 1000 character error

    await job_tracker.record_job_failure("test_job", long_error)

    status = await job_tracker.get_job_status("test_job")
    assert len(status["last_error"]) == 500  # Should be truncated to 500
