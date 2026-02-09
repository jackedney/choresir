"""Pytest configuration and shared fixtures."""

import asyncio
import logging
import secrets
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite
import pytest
from fastapi.testclient import TestClient

import src.core.db_client as db_module
from src.core.config import Settings
from src.core.db_client import (
    create_record,
    delete_record,
    init_db,
    list_records,
)
from src.core.schema import TABLES
from src.main import app


logger = logging.getLogger(__name__)


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create fresh temp SQLite file per test and initialize schema.

    Args:
        tmp_path: Pytest fixture providing temporary directory path

    Yields:
        Path to the temporary SQLite database file

    Cleanup:
        Temp file is automatically cleaned up by pytest's tmp_path fixture
    """
    db_file = tmp_path / "test.db"
    asyncio.run(init_db(db_path=str(db_file)))
    yield db_file


@pytest.fixture
def test_settings(sqlite_db: Path) -> Settings:
    """Override settings for testing with SQLite configuration."""
    return Settings(
        sqlite_db_path=str(sqlite_db),
        openrouter_api_key="test_key",
        waha_base_url="http://waha:3000",
        waha_webhook_secret="test_secret",
        admin_password="test_admin",
        secret_key="test_key",
        logfire_token="test_logfire",
        model_id="anthropic/claude-3.5-sonnet",
        is_production=False,
    )


@pytest.fixture
async def db_client(sqlite_db: Path) -> AsyncGenerator[None, None]:
    """Provide clean database for each test.

    This fixture patches the db_client module to use the test SQLite database
    and cleans up all records between tests.

    Args:
        sqlite_db: Path to the test SQLite database

    Yields:
        None - The db_client module functions are patched to use the test database
    """

    async def test_get_connection(*, db_path: str | None = None) -> Any:
        """Override get_connection to use the test database path."""
        conn = await aiosqlite.connect(str(sqlite_db))
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        return conn

    original_conn: Any = db_module.get_connection
    db_module.get_connection = test_get_connection  # type: ignore[valid-type]

    yield

    db_module.get_connection = original_conn


@pytest.fixture
def test_client(test_settings: Settings) -> TestClient:
    """Provide a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
async def sample_users(db_client) -> dict[str, dict]:
    """Create sample members for testing."""
    members = {
        "alice": {
            "phone": "+15551234567",
            "name": "Alice Admin",
            "role": "admin",
            "status": "active",
        },
        "bob": {
            "phone": "+15557654321",
            "name": "Bob Member",
            "role": "member",
            "status": "active",
        },
        "charlie": {
            "phone": "+15559876543",
            "name": "Charlie Member",
            "role": "member",
            "status": "active",
        },
    }

    created = {}
    for key, data in members.items():
        created[key] = await create_record(collection="members", data=data)

    return created


async def create_test_admin(phone: str, name: str) -> dict[str, Any]:
    """Create admin member for testing, bypassing normal join workflow.

    This is a test helper - in production, admins are created through
    the normal onboarding process (via request_join) and promoted manually.

    NOTE: This uses raw db operations intentionally for test setup,
    but should ONLY be used in test fixtures or conftest.py helpers.
    Production code and test workflows must use the service layer.

    Args:
        phone: Admin's phone number in E.164 format
        name: Admin's display name

    Returns:
        Created admin member record
    """
    admin_data = {
        "phone": phone,
        "name": name,
        "role": "admin",
        "status": "active",
    }
    return await create_record(collection="members", data=admin_data)


@pytest.fixture
async def sample_chores(db_client, sample_users: dict) -> dict[str, dict]:
    """Create sample chores for testing."""
    chores = {
        "dishes": {
            "title": "Wash Dishes",
            "description": "Clean all dishes in the sink",
            "schedule_cron": "0 20 * * *",
            "assigned_to": sample_users["bob"]["id"],
            "current_state": "TODO",
            "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
        "trash": {
            "title": "Take Out Trash",
            "description": "Empty all trash bins",
            "schedule_cron": "0 9 * * 1",
            "assigned_to": sample_users["charlie"]["id"],
            "current_state": "TODO",
            "deadline": (datetime.now(UTC) + timedelta(days=4)).isoformat(),
        },
    }

    created = {}
    for key, data in chores.items():
        created[key] = await create_record(collection="chores", data=data)

    return created


@pytest.fixture
def user_factory() -> Any:
    """Factory for creating members with custom data.

    Usage:
        user = await user_factory(name="Test User", phone="+1234567890", role="admin")
    """

    async def _create_user(**kwargs):
        random_suffix = "".join(secrets.choice("0123456789") for _ in range(10))
        member_data = {
            "phone": kwargs.get("phone", f"+1{random_suffix}"),
            "name": kwargs.get("name", f"User {uuid.uuid4().hex[:8]}"),
            "role": kwargs.get("role", "member"),
            "status": kwargs.get("status", "active"),
        }
        return await create_record(collection="members", data=member_data)

    return _create_user


@pytest.fixture
def chore_factory() -> Any:
    """Factory for creating chores with custom data.

    Usage:
        chore = await chore_factory(title="Test Chore", assigned_to=user_id, current_state="TODO")
    """

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

        return await create_record(collection="chores", data=chore_data)

    return _create_chore


@pytest.fixture
async def clean_db(sqlite_db: Path) -> AsyncGenerator[None, None]:
    """Ensure clean database state, failing loudly on cleanup errors.

    This fixture ensures cleanup happens after the test,
    failing the test if cleanup encounters any errors.
    """
    yield

    cleanup_errors = []
    for table in reversed(TABLES):
        try:
            records = await list_records(collection=table)
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
