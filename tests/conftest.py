"""Pytest configuration and shared fixtures."""

import asyncio
import contextlib
import logging
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.schema import COLLECTIONS, sync_schema
from src.main import app


# Import pocketbase only for integration tests
try:
    from pocketbase import PocketBase
    from pocketbase.client import ClientResponseError

    POCKETBASE_AVAILABLE = True
except ImportError:
    POCKETBASE_AVAILABLE = False

    class PocketBase:  # type: ignore[no-redef]
        """Stub PocketBase class for when the library is not available."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("pocketbase is not installed")

    class ClientResponseError(Exception):  # type: ignore[no-redef]
        """Stub ClientResponseError for when pocketbase is not available."""

        status: int = 0


# HTTP status codes
HTTP_NOT_FOUND = 404


logger = logging.getLogger(__name__)


# Shared test utilities


class MockDBClient:
    """Mock database client that mimics src.core.db_client module interface.

    This wrapper provides async methods that match the production db_client module,
    but uses a test PocketBase instance internally.
    """

    def __init__(self, pb_instance: PocketBase):
        self._pb = pb_instance

    async def create_record(self, *, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new record in the specified collection."""
        try:
            record = self._pb.collection(collection).create(data)
            return record.__dict__
        except ClientResponseError as e:
            msg = f"Failed to create record in {collection}: {e}"
            raise RuntimeError(msg) from e

    async def get_record(self, *, collection: str, record_id: str) -> dict[str, Any]:
        """Get a record by ID from the specified collection."""
        try:
            record = self._pb.collection(collection).get_one(record_id)
            return record.__dict__
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                msg = f"Record {record_id} not found in {collection}"
                raise KeyError(msg) from e
            msg = f"Failed to get record from {collection}: {e}"
            raise RuntimeError(msg) from e

    async def update_record(self, *, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a record in the specified collection."""
        try:
            record = self._pb.collection(collection).update(record_id, data)
            return record.__dict__
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                msg = f"Record {record_id} not found in {collection}"
                raise KeyError(msg) from e
            msg = f"Failed to update record in {collection}: {e}"
            raise RuntimeError(msg) from e

    async def delete_record(self, *, collection: str, record_id: str) -> None:
        """Delete a record from the specified collection."""
        try:
            self._pb.collection(collection).delete(record_id)
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                msg = f"Record {record_id} not found in {collection}"
                raise KeyError(msg) from e
            msg = f"Failed to delete record from {collection}: {e}"
            raise RuntimeError(msg) from e

    async def list_records(
        self,
        *,
        collection: str,
        page: int = 1,
        per_page: int = 50,
        filter_query: str = "",
        sort: str = "",
    ) -> list[dict[str, Any]]:
        """List records from the specified collection with filtering and pagination."""
        try:
            # Only include filter and sort in query_params if they're not empty
            query_params = {}
            if sort:
                query_params["sort"] = sort
            if filter_query:
                query_params["filter"] = filter_query

            result = self._pb.collection(collection).get_list(
                page=page,
                per_page=per_page,
                query_params=query_params,
            )
            return [item.__dict__ for item in result.items]
        except ClientResponseError as e:
            msg = f"Failed to list records from {collection}: {e}"
            raise RuntimeError(msg) from e

    async def get_first_record(self, *, collection: str, filter_query: str) -> dict[str, Any] | None:
        """Get the first record matching the filter query, or None if not found."""
        try:
            result = self._pb.collection(collection).get_first_list_item(filter_query)
            return result.__dict__
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                return None
            msg = f"Failed to get first record from {collection}: {e}"
            raise RuntimeError(msg) from e


@pytest.fixture(scope="session")
def pocketbase_server() -> Generator[str]:
    """Start ephemeral PocketBase instance for testing."""
    if not POCKETBASE_AVAILABLE:
        pytest.skip("PocketBase not available - skipping integration test")
    pb_data_dir = tempfile.mkdtemp(prefix="pb_test_")
    pb_binary = shutil.which("pocketbase")

    if pb_binary is None:
        pytest.skip("PocketBase binary not found in PATH")

    assert pb_binary is not None  # For type checker (pytest.skip already handles None case)

    # Disable automigrate and set migrationsDir to the ephemeral data dir to prevent
    # stray migration files (e.g., in system temp) from causing failures.
    # This project uses a code-first schema approach (src/core/schema.py) instead
    # of PocketBase migrations.
    process = subprocess.Popen(
        [
            pb_binary,
            "serve",
            "--dir",
            pb_data_dir,
            "--http",
            "127.0.0.1:8091",
            "--automigrate=false",
            f"--migrationsDir={pb_data_dir}/migrations",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    pb_url = "http://127.0.0.1:8091"
    max_wait = 10  # seconds
    start_time = time.time()

    # Wait for PocketBase to be ready
    while time.time() - start_time < max_wait:
        try:
            client = PocketBase(pb_url)
            client.health.check()
            break
        except Exception:
            time.sleep(0.5)
    else:
        # Capture output for debugging
        stdout, stderr = b"", b""
        with contextlib.suppress(Exception):
            stdout, stderr = process.communicate(timeout=1)
        process.kill()
        shutil.rmtree(pb_data_dir, ignore_errors=True)
        error_msg = "PocketBase failed to start within 10 seconds"
        if stdout:
            error_msg += f"\nStdout: {stdout.decode()[:500]}"
        if stderr:
            error_msg += f"\nStderr: {stderr.decode()[:500]}"
        pytest.fail(error_msg)

    # Give PocketBase a moment to fully initialize
    time.sleep(1)

    # Create admin user for schema management
    try:
        # Set BROWSER to empty string to prevent PocketBase from opening a browser
        env = {"BROWSER": "", **os.environ}
        result = subprocess.run(
            [
                pb_binary,
                "superuser",
                "upsert",
                "admin@test.local",
                "testpassword123",
                "--dir",
                pb_data_dir,
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        logger.info(f"Admin user creation output: {result.stdout}")
        if result.stderr:
            logger.warning(f"Admin user creation stderr: {result.stderr}")

        # Give time for admin to be persisted
        time.sleep(1)

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create admin user: {e.stderr}")
        process.kill()
        shutil.rmtree(pb_data_dir, ignore_errors=True)
        pytest.fail(f"Failed to create admin user: {e.stderr}")

    yield pb_url

    process.kill()
    process.wait()
    shutil.rmtree(pb_data_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def test_settings(pocketbase_server: str) -> Settings:
    """Override settings for testing."""
    return Settings(
        pocketbase_url=pocketbase_server,
        pocketbase_admin_email="admin@test.local",
        pocketbase_admin_password="testpassword123",
        openrouter_api_key="test_key",
        waha_base_url="http://waha:3000",
        logfire_token="test_logfire",
        model_id="anthropic/claude-3.5-sonnet",
    )


@pytest.fixture(scope="session")
def initialized_db(pocketbase_server: str, test_settings: Settings) -> PocketBase:
    """Initialize PocketBase schema and return authenticated client."""
    asyncio.run(
        sync_schema(
            admin_email="admin@test.local",
            admin_password="testpassword123",
            pocketbase_url=pocketbase_server,
        )
    )

    # Create authenticated client for tests
    client = PocketBase(pocketbase_server)
    client.admins.auth_with_password("admin@test.local", "testpassword123")

    return client


# @pytest.fixture
# def mock_db_module(initialized_db: PocketBase, test_settings: Settings, monkeypatch):
#     """Patch the db_client module to use the test PocketBase instance."""
#     # NOTE: This fixture is commented out as it references undefined mock functions
#     # For integration tests, use the real db_client with a test PocketBase instance
#     yield


@pytest.fixture
def db_client(initialized_db: PocketBase) -> Generator[MockDBClient]:
    """Provide clean database for each test with async wrapper interface."""
    # Clean in reverse dependency order: logs → chores → users
    for collection in reversed(COLLECTIONS):
        try:
            records = initialized_db.collection(collection).get_full_list()
            for record in records:
                initialized_db.collection(collection).delete(record.id)
        except Exception as e:
            logger.warning(f"Failed to clean collection {collection}: {e}")

    yield MockDBClient(initialized_db)


@pytest.fixture
def test_client(test_settings: Settings) -> TestClient:
    """Provide FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_users(db_client: MockDBClient, initialized_db: PocketBase) -> dict[str, dict]:
    """Create sample users for testing."""
    users = {
        "alice": {
            "phone": "+15551234567",
            "name": "Alice Admin",
            "email": "alice@test.local",
            "role": "admin",
            "status": "active",
            "password": "test_password",
            "passwordConfirm": "test_password",
        },
        "bob": {
            "phone": "+15557654321",
            "name": "Bob Member",
            "email": "bob@test.local",
            "role": "member",
            "status": "active",
            "password": "test_password",
            "passwordConfirm": "test_password",
        },
        "charlie": {
            "phone": "+15559876543",
            "name": "Charlie Member",
            "email": "charlie@test.local",
            "role": "member",
            "status": "active",
            "password": "test_password",
            "passwordConfirm": "test_password",
        },
    }

    created = {}
    for key, data in users.items():
        record = initialized_db.collection("users").create(data)
        created[key] = record.__dict__

    return created


async def create_test_admin(phone: str, name: str, db_client: MockDBClient) -> dict[str, Any]:
    """Create admin user for testing, bypassing normal join workflow.

    This is a test helper - in production, admins are created through
    the normal onboarding process (via request_join) and promoted manually.

    NOTE: This uses raw db operations intentionally for test setup,
    but should ONLY be used in test fixtures or conftest.py helpers.
    Production code and test workflows must use the service layer.

    Args:
        phone: Admin's phone number in E.164 format
        name: Admin's display name
        db_client: Mock database client

    Returns:
        Created admin user record
    """
    # Generate email from phone for auth collection requirement
    email = f"{phone.replace('+', '')}@test.local"
    admin_data = {
        "phone": phone,
        "name": name,
        "email": email,
        "role": "admin",
        "status": "active",
        "password": "test_password",
        "passwordConfirm": "test_password",
    }
    return await db_client.create_record(collection="users", data=admin_data)


@pytest.fixture
def sample_chores(db_client: MockDBClient, initialized_db: PocketBase, sample_users: dict) -> dict[str, dict]:
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
        record = initialized_db.collection("chores").create(data)
        created[key] = record.__dict__

    return created


# Factory fixtures for flexible test data creation


@pytest.fixture
def user_factory(initialized_db: PocketBase):
    """Factory for creating users with custom data.

    Usage:
        user = user_factory(name="Test User", phone="+1234567890", role="admin")
    """

    def _create_user(**kwargs):
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
        # Allow override of any fields
        user_data.update({k: v for k, v in kwargs.items() if k not in user_data})
        record = initialized_db.collection("users").create(user_data)
        return record.__dict__

    return _create_user


@pytest.fixture
def chore_factory(initialized_db: PocketBase):
    """Factory for creating chores with custom data.

    Usage:
        chore = chore_factory(title="Test Chore", assigned_to=user_id, current_state="TODO")
    """

    def _create_chore(**kwargs):
        chore_data = {
            "title": kwargs.get("title", f"Chore {uuid.uuid4().hex[:8]}"),
            "description": kwargs.get("description", "A test chore"),
            "schedule_cron": kwargs.get("schedule_cron", "0 10 * * *"),
            "current_state": kwargs.get("current_state", "TODO"),
        }
        # Conditionally add assigned_to and deadline if provided
        if "assigned_to" in kwargs:
            chore_data["assigned_to"] = kwargs["assigned_to"]
        if "deadline" in kwargs:
            chore_data["deadline"] = kwargs["deadline"]

        # Allow override of any fields
        chore_data.update({k: v for k, v in kwargs.items() if k not in chore_data})
        record = initialized_db.collection("chores").create(chore_data)
        return record.__dict__

    return _create_chore


@pytest.fixture
def clean_db(db_client: MockDBClient) -> Generator[MockDBClient]:
    """Ensure clean database state, failing loudly on cleanup errors.

    This fixture provides the db_client and ensures cleanup happens after the test,
    failing the test if cleanup encounters any errors.
    """
    yield db_client

    # Cleanup after test - fail loudly if errors occur
    collections = ["verifications", "chores", "users", "conflicts"]
    cleanup_errors = []

    for collection in collections:
        try:
            records = asyncio.run(db_client.list_records(collection=collection))
            for record in records:
                try:
                    asyncio.run(db_client.delete_record(collection=collection, record_id=record["id"]))
                except Exception as e:
                    cleanup_errors.append(f"{collection}/{record['id']}: {e!s}")
        except Exception as e:
            cleanup_errors.append(f"{collection} (list): {e!s}")

    if cleanup_errors:
        error_msg = "Database cleanup failed:\n" + "\n".join(cleanup_errors)
        pytest.fail(error_msg)
