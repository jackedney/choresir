"""Pytest configuration and shared fixtures."""

import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.db_client import (
    create_record,
    delete_record,
    list_records,
)
from src.core.schema import init_db
from src.main import app


logger = __import__("logging").getLogger(__name__)


@pytest.fixture(scope="session")
def temp_db_path() -> Generator[Path]:
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
def test_client(test_settings: Settings) -> TestClient:
    """Provide FastAPI test client."""
    return TestClient(app)


@pytest.fixture
async def sample_users(clean_db) -> dict[str, dict]:
    """Create sample users for testing."""
    users = {
        "alice": await create_record(
            collection="members",
            data={
                "phone": "+15551234567",
                "name": "Alice Admin",
                "role": "admin",
                "status": "active",
            },
        ),
        "bob": await create_record(
            collection="members",
            data={
                "phone": "+15557654321",
                "name": "Bob Member",
                "role": "member",
                "status": "active",
            },
        ),
        "charlie": await create_record(
            collection="members",
            data={
                "phone": "+15559876543",
                "name": "Charlie Member",
                "role": "member",
                "status": "active",
            },
        ),
    }

    return users


async def create_test_admin(phone: str, name: str, db_client: Any = None) -> dict[str, Any]:
    """Create admin user for testing, bypassing normal join workflow.

    This is a test helper - in production, admins are created through
    the normal onboarding process (via request_join) and promoted manually.

    NOTE: This uses raw db operations intentionally for test setup,
    but should ONLY be used in test fixtures or conftest.py helpers.
    Production code and test workflows must use the service layer.

    Args:
        phone: Admin's phone number in E.164 format
        name: Admin's display name
        db_client: Database client (unused, kept for backward compatibility)

    Returns:
        Created admin user record
    """
    admin_data = {
        "phone": phone,
        "name": name,
        "role": "admin",
        "status": "active",
    }
    return await create_record(collection="members", data=admin_data)


@pytest.fixture
async def sample_chores(clean_db, sample_users: dict[str, dict]) -> dict[str, dict]:
    """Create sample chores for testing."""
    chores = {
        "dishes": await create_record(
            collection="chores",
            data={
                "title": "Wash Dishes",
                "description": "Clean all dishes in the sink",
                "schedule_cron": "0 20 * * *",
                "assigned_to": sample_users["bob"]["id"],
                "current_state": "TODO",
                "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        ),
        "trash": await create_record(
            collection="chores",
            data={
                "title": "Take Out Trash",
                "description": "Empty all trash bins",
                "schedule_cron": "0 9 * * 1",
                "assigned_to": sample_users["charlie"]["id"],
                "current_state": "TODO",
                "deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(),
            },
        ),
    }

    return chores


@pytest.fixture
async def user_factory(clean_db):
    """Factory for creating users with custom data.

    Usage:
        user = await user_factory(name="Test User", phone="+1234567890", role="admin")
    """

    import secrets

    async def _create_user(**kwargs):
        import uuid

        random_suffix = "".join(secrets.choice("0123456789") for _ in range(10))
        user_data = {
            "phone": kwargs.get("phone", f"+1{random_suffix}"),
            "name": kwargs.get("name", f"User {uuid.uuid4().hex[:8]}"),
            "role": kwargs.get("role", "member"),
            "status": kwargs.get("status", "active"),
        }

        user_data.update({k: v for k, v in kwargs.items() if k not in user_data})
        return await create_record(collection="members", data=user_data)

    return _create_user


@pytest.fixture
async def chore_factory(clean_db):
    """Factory for creating chores with custom data.

    Usage:
        chore = await chore_factory(title="Test Chore", assigned_to=user_id, current_state="TODO")
    """
    import uuid

    async def _create_chore(**kwargs):
        chore_data = {
            "title": kwargs.get("title", f"Chore {uuid.uuid4().hex[:8]}"),
            "description": kwargs.get("description", "A test chore"),
            "schedule_cron": kwargs.get("schedule_cron", "0 10 * * *"),
            "current_state": kwargs.get("current_state", "TODO"),
        }

        if "assigned_to" in kwargs:
            chore_data["assigned_to"] = kwargs["assigned_to"]
        if "deadline" in kwargs:
            chore_data["deadline"] = kwargs["deadline"]

        chore_data.update({k: v for k, v in kwargs.items() if k not in chore_data})
        return await create_record(collection="chores", data=chore_data)

    return _create_chore
