"""Tests for scheduler health check endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for FastAPI app."""
    return TestClient(app)


@pytest.mark.unit
def test_health_endpoint_returns_healthy(client: TestClient) -> None:
    """Test that health endpoint returns healthy status."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.unit
def test_scheduler_health_endpoint_all_jobs_healthy(client: TestClient) -> None:
    """Test scheduler health endpoint when all jobs are healthy."""
    mock_job_status = {
        "job_name": "test_job",
        "last_success": "2024-01-01T00:00:00Z",
        "last_failure": None,
        "last_error": None,
        "consecutive_failures": 0,
        "success_count": 10,
        "failure_count": 0,
        "currently_running": False,
        "current_run_started": None,
    }

    with patch("src.core.scheduler_tracker.job_tracker") as mock_tracker:
        mock_tracker.get_job_status = AsyncMock(return_value=mock_job_status)
        mock_tracker.get_dead_letter_queue = lambda: []

        response = client.get("/health/scheduler")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "jobs" in data
        assert data["dead_letter_queue_size"] == 0


@pytest.mark.unit
def test_scheduler_health_endpoint_degraded_with_failures(client: TestClient) -> None:
    """Test scheduler health endpoint when jobs have failures."""
    mock_job_status = {
        "job_name": "test_job",
        "last_success": "2024-01-01T00:00:00Z",
        "last_failure": "2024-01-01T01:00:00Z",
        "last_error": "Test error",
        "consecutive_failures": 1,
        "success_count": 10,
        "failure_count": 1,
        "currently_running": False,
        "current_run_started": None,
    }

    with patch("src.core.scheduler_tracker.job_tracker") as mock_tracker:
        mock_tracker.get_job_status = AsyncMock(return_value=mock_job_status)
        mock_tracker.get_dead_letter_queue = lambda: []

        response = client.get("/health/scheduler")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"


@pytest.mark.unit
def test_scheduler_health_endpoint_critical_with_dlq(client: TestClient) -> None:
    """Test scheduler health endpoint when jobs are in dead letter queue."""
    mock_job_status = {
        "job_name": "test_job",
        "last_success": None,
        "last_failure": "2024-01-01T01:00:00Z",
        "last_error": "Persistent error",
        "consecutive_failures": 3,
        "success_count": 0,
        "failure_count": 3,
        "currently_running": False,
        "current_run_started": None,
    }

    mock_dlq = [
        {
            "job_name": "test_job",
            "error": "Persistent error",
            "context": "Failed 3 consecutive times",
        }
    ]

    with patch("src.core.scheduler_tracker.job_tracker") as mock_tracker:
        mock_tracker.get_job_status = AsyncMock(return_value=mock_job_status)
        mock_tracker.get_dead_letter_queue = lambda: mock_dlq

        response = client.get("/health/scheduler")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "critical"
        assert data["dead_letter_queue_size"] == 1
        assert len(data["dead_letter_queue"]) == 1
