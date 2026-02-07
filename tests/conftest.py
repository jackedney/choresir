"""Pytest configuration and shared fixtures."""

import asyncio
import logging
import secrets
import tempfile
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core import config
from src.core.db_client import create_record, get_db, close_db, delete_record, list_records
from src.core.schema import COLLECTIONS, init_db
from src.main import app


logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary file for the SQLite database."""
    # Create a temp file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    yield db_path

    # Cleanup
    try:
        Path(db_path).unlink(missing_ok=True)
        # Also remove shm and wal files if they exist (WAL mode)
        Path(f"{db_path}-shm").unlink(missing_ok=True)
        Path(f"{db_path}-wal").unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup temp db: {e}")


@pytest.fixture(scope="session", autouse=True)
def configure_test_settings(temp_db_path: str) -> Generator[None, None, None]:
    """Configure settings to use the temporary database."""
    original_path = config.settings.sqlite_db_path
    original_code = config.settings.house_code
    original_pass = config.settings.house_password

    config.settings.sqlite_db_path = temp_db_path
    config.settings.house_code = "TEST123"
    config.settings.house_password = "testpass"

    yield

    config.settings.sqlite_db_path = original_path
    config.settings.house_code = original_code
    config.settings.house_password = original_pass


@pytest.fixture(autouse=True)
async def manage_database(configure_test_settings: None) -> AsyncGenerator[None, None]:
    """Initialize and clean database for each test."""
    # Initialize schema (idempotent)
    await init_db()

    # Clean data
    db = await get_db()
    await db.execute("PRAGMA foreign_keys = OFF")
    for collection in COLLECTIONS:
        try:
            await db.execute(f"DELETE FROM {collection}")
        except Exception as e:
            logger.warning(f"Failed to clean table {collection}: {e}")
    await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()

    yield

    # Close connection to avoid loop mismatch errors
    await close_db()


@pytest.fixture
def clean_db(manage_database) -> None:
    """Fixture alias for tests that explicitly request clean db."""
    # The autouse fixture manage_database already handles cleaning.
    # This alias ensures tests requesting clean_db don't fail setup.
    return None


@pytest.fixture
def test_client() -> TestClient:
    """Provide FastAPI test client."""
    return TestClient(app)


# Factory fixtures for flexible test data creation

@pytest.fixture
def user_factory():
    """Factory for creating users with custom data."""
    async def _create_user(**kwargs):
        random_suffix = "".join(secrets.choice("0123456789") for _ in range(10))
        user_data = {
            "phone": kwargs.get("phone", f"+1{random_suffix}"),
            "name": kwargs.get("name", f"User {uuid.uuid4().hex[:8]}"),
            "email": kwargs.get("email", f"user_{uuid.uuid4().hex[:8]}@test.local"),
            "role": kwargs.get("role", "member"),
            "status": kwargs.get("status", "active"),
            "password": kwargs.get("password", "test_password"),
            "passwordConfirm": kwargs.get("password", "test_password"),
        }
        # Allow override
        user_data.update({k: v for k, v in kwargs.items() if k not in user_data})
        return await create_record(collection="users", data=user_data)

    return _create_user


@pytest.fixture
def chore_factory():
    """Factory for creating chores with custom data."""
    async def _create_chore(**kwargs):
        chore_data = {
            "title": kwargs.get("title", f"Chore {uuid.uuid4().hex[:8]}"),
            "description": kwargs.get("description", "A test chore"),
            "schedule_cron": kwargs.get("schedule_cron", "0 10 * * *"),
            "current_state": kwargs.get("current_state", "TODO"),
            # assigned_to and deadline usually required
        }
        if "assigned_to" in kwargs:
            chore_data["assigned_to"] = kwargs["assigned_to"]
        if "deadline" in kwargs:
            chore_data["deadline"] = kwargs["deadline"]
        else:
            # Default deadline tomorrow
            chore_data["deadline"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()

        chore_data.update({k: v for k, v in kwargs.items() if k not in chore_data})
        return await create_record(collection="chores", data=chore_data)

    return _create_chore


@pytest.fixture
async def sample_users(user_factory) -> dict[str, dict]:
    """Create sample users for testing."""
    alice = await user_factory(name="Alice Admin", role="admin", phone="+15551234567")
    bob = await user_factory(name="Bob Member", role="member", phone="+15557654321")
    charlie = await user_factory(name="Charlie Member", role="member", phone="+15559876543")

    return {
        "alice": alice,
        "bob": bob,
        "charlie": charlie
    }


@pytest.fixture
async def sample_chores(chore_factory, sample_users) -> dict[str, dict]:
    """Create sample chores for testing."""
    dishes = await chore_factory(
        title="Wash Dishes",
        assigned_to=sample_users["bob"]["id"],
        schedule_cron="0 20 * * *"
    )
    trash = await chore_factory(
        title="Take Out Trash",
        assigned_to=sample_users["charlie"]["id"],
        schedule_cron="0 9 * * 1"
    )

    return {
        "dishes": dishes,
        "trash": trash
    }
