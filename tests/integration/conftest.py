"""Pytest configuration and fixtures for integration tests."""

import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.agents import choresir_agent as choresir_agent_module
from src.agents.retry_handler import reset_retry_handler
from src.core import admin_notifier as admin_notifier_module, config as config_module, db_client as db_module
from src.core.config import Settings
from src.core.db_client import (
    create_record,
    delete_record,
    get_first_record,
    get_record,
    list_records,
    update_record,
)
from src.core.schema import init_db
from src.services import user_service as user_service_module


logger = __import__("logging").getLogger(__name__)


@pytest.fixture(scope="session")
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary SQLite database file for the test session.

    The database file is created and initialized at the start of the session,
    and cleaned up after all tests complete.
    """
    temp_dir = tempfile.mkdtemp(prefix="test_db_")
    db_path = Path(temp_dir) / "test.db"

    yield db_path

    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
async def test_db(temp_db_path: Path) -> AsyncGenerator[None, None]:
    """Initialize the test SQLite database with all tables.

    This fixture runs once per test session to initialize the database schema.
    Tests should use the db_client functions directly to interact with the database.
    """
    await init_db(db_path=str(temp_db_path))
    logger.info(f"Test database initialized at {temp_db_path}")
    yield


@pytest.fixture(scope="session")
def test_settings(temp_db_path: Path) -> Settings:
    """Override settings for testing.

    Uses the temporary database path from the temp_db_path fixture.
    """
    return Settings(
        openrouter_api_key="test_key",
        waha_base_url="http://waha:3000",
        logfire_token="test_logfire",
        house_name="TestHouse",
        house_code="TEST123",
        house_password="testpass",
        model_id="anthropic/claude-3.5-sonnet",
        sqlite_db_path=str(temp_db_path),
    )


@pytest.fixture
async def clean_db(test_db) -> AsyncGenerator[None, None]:
    """Ensure clean database state for each test.

    Cleans all tables before each test to ensure test isolation.
    """
    from src.core.schema import TABLES

    tables = TABLES
    for table in tables:
        try:
            records = await list_records(collection=table, per_page=1000)
            for record in records:
                await delete_record(collection=table, record_id=record["id"])
        except Exception as e:
            logger.warning(f"Failed to clean table {table}: {e}")

    yield

    cleanup_errors = []

    for table in ["verifications", "chores", "users", "conflicts"]:
        try:
            records = await list_records(collection=table, per_page=1000)
            for record in records:
                try:
                    await delete_record(collection=table, record_id=record["id"])
                except Exception as e:
                    cleanup_errors.append(f"{table}/{record['id']}: {e!s}")
        except Exception as e:
            cleanup_errors.append(f"{table} (list): {e!s}")

    if cleanup_errors:
        error_msg = "Database cleanup failed:\n" + "\n".join(cleanup_errors)
        pytest.fail(error_msg)


@pytest.fixture
def db_client():
    """Provide db_client module for tests.

    In the new SQLite approach, tests can use the db_client module
    functions directly. This fixture provides backward compatibility with
    tests that expect a db_client object.
    """

    class _DBClient:
        """Adapter class for backward compatibility with MockDBClient interface."""

        _pb = None  # Kept for backward compatibility

        async def create_record(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
            return await create_record(collection=collection, data=data)

        async def get_record(self, collection: str, record_id: str) -> dict[str, Any]:
            return await get_record(collection=collection, record_id=record_id)

        async def update_record(self, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
            return await update_record(collection=collection, record_id=record_id, data=data)

        async def delete_record(self, collection: str, record_id: str) -> None:
            await delete_record(collection=collection, record_id=record_id)

        async def list_records(
            self,
            collection: str,
            page: int = 1,
            per_page: int = 50,
            filter_query: str = "",
            sort: str = "",
        ) -> list[dict[str, Any]]:
            return await list_records(
                collection=collection,
                page=page,
                per_page=per_page,
                filter_query=filter_query,
                sort=sort,
            )

        async def get_first_record(self, collection: str, filter_query: str) -> dict[str, Any] | None:
            return await get_first_record(collection=collection, filter_query=filter_query)

    return _DBClient()


@pytest.fixture
def mock_db_module(test_settings: Settings, monkeypatch):
    """Patch db_client module and settings for testing with SQLite.

    This fixture replaces the old PocketBase-based mock_db_module with
    SQLite-compatible patches. It ensures tests use the test database
    path and settings.
    """
    # Patch global settings to use test settings
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(db_module, "settings", test_settings)
    monkeypatch.setattr(user_service_module, "settings", test_settings)
    monkeypatch.setattr(admin_notifier_module, "settings", test_settings)
    monkeypatch.setattr(choresir_agent_module, "settings", test_settings)

    yield


@pytest.fixture
async def sample_users(clean_db) -> dict[str, dict]:
    """Create sample users for testing."""
    users = []
    for _, (_key, phone, name, role) in enumerate(
        [
            ("alice", "+1234567890", "Alice Admin", "admin"),
            ("bob", "+1234567891", "Bob Member", "member"),
            ("charlie", "+1234567892", "Charlie Member", "member"),
        ],
        start=1,
    ):
        users.append(
            await create_record(
                collection="members",
                data={
                    "phone": phone,
                    "name": name,
                    "role": role,
                    "status": "active",
                },
            )
        )

    return {key: user for key, user in zip(["alice", "bob", "charlie"], users, strict=True)}


@pytest.fixture
async def sample_chores(clean_db, sample_users: dict[str, dict]) -> list[dict]:
    """Create sample chores for testing."""
    chores_data = [
        {
            "title": "Wash dishes",
            "description": "Clean all dishes in the sink",
            "assigned_to": sample_users["alice"]["id"],
            "schedule_cron": "0 20 * * *",
            "current_state": "TODO",
            "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
        {
            "title": "Take out trash",
            "description": "Take trash bins to curb",
            "assigned_to": sample_users["bob"]["id"],
            "schedule_cron": "0 9 * * 1",
            "current_state": "TODO",
            "deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(),
        },
        {
            "title": "Vacuum living room",
            "description": "Vacuum the entire living room",
            "assigned_to": sample_users["alice"]["id"],
            "schedule_cron": "0 10 * * 6",
            "current_state": "TODO",
            "deadline": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    ]

    created_chores = []
    for chore_data in chores_data:
        chore = await create_record(collection="chores", data=chore_data)
        created_chores.append(chore)

    return created_chores


@pytest.fixture(autouse=True)
def reset_agent_retry_handler():
    """Reset the global retry handler before each test to ensure clean state."""
    reset_retry_handler()
    yield
    reset_retry_handler()


@pytest.fixture(autouse=True)
def mock_retry_handler_sleep():
    """Mock asyncio.sleep in retry handler to avoid actual delays in integration tests.

    The retry handler uses asyncio.sleep for exponential backoff between retries.
    In tests, we want to verify the retry behavior without waiting for actual delays.
    """
    from unittest.mock import AsyncMock, patch

    with patch("src.agents.retry_handler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep
