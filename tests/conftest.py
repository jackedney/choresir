"""Pytest configuration and fixtures for integration tests."""

import asyncio
import logging
import shutil
import subprocess
import tempfile
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pocketbase import PocketBase
from pocketbase.client import ClientResponseError

from src.core import db_client as db_module
from src.core.config import Settings
from src.core.db_client import DatabaseError, RecordNotFoundError
from src.core.schema import COLLECTIONS, sync_schema
from src.main import app


# HTTP status codes
HTTP_NOT_FOUND = 404


logger = logging.getLogger(__name__)


# Helper functions for mock_db_module fixture
def _make_mock_create_record(pb: PocketBase):
    """Create mock create_record function."""

    async def mock_create_record(*, collection: str, data: dict) -> dict:
        try:
            record = pb.collection(collection).create(data)
            return record.__dict__
        except Exception as e:
            raise DatabaseError(f"Failed to create record in {collection}: {e}") from e

    return mock_create_record


def _make_mock_get_record(pb: PocketBase):
    """Create mock get_record function."""

    async def mock_get_record(*, collection: str, record_id: str) -> dict:
        try:
            record = pb.collection(collection).get_one(record_id)
            return record.__dict__
        except Exception as e:
            if hasattr(e, "status") and e.status == HTTP_NOT_FOUND:
                raise RecordNotFoundError(f"Record not found in {collection}: {record_id}") from e
            raise DatabaseError(f"Failed to get record from {collection}: {e}") from e

    return mock_get_record


def _make_mock_update_record(pb: PocketBase):
    """Create mock update_record function."""

    async def mock_update_record(*, collection: str, record_id: str, data: dict) -> dict:
        try:
            record = pb.collection(collection).update(record_id, data)
            return record.__dict__
        except Exception as e:
            if hasattr(e, "status") and e.status == HTTP_NOT_FOUND:
                raise RecordNotFoundError(f"Record not found in {collection}: {record_id}") from e
            raise DatabaseError(f"Failed to update record in {collection}: {e}") from e

    return mock_update_record


def _make_mock_delete_record(pb: PocketBase):
    """Create mock delete_record function."""

    async def mock_delete_record(*, collection: str, record_id: str) -> None:
        try:
            pb.collection(collection).delete(record_id)
        except Exception as e:
            if hasattr(e, "status") and e.status == HTTP_NOT_FOUND:
                raise RecordNotFoundError(f"Record not found in {collection}: {record_id}") from e
            raise DatabaseError(f"Failed to delete record from {collection}: {e}") from e

    return mock_delete_record


def _make_mock_list_records(pb: PocketBase):
    """Create mock list_records function."""

    async def mock_list_records(
        *,
        collection: str,
        page: int = 1,
        per_page: int = 50,
        filter_query: str = "",
        sort: str = "-created",
    ) -> list[dict]:
        try:
            result = pb.collection(collection).get_list(
                page=page,
                per_page=per_page,
                query_params={"filter": filter_query, "sort": sort},
            )
            return [item.__dict__ for item in result.items]
        except Exception as e:
            raise DatabaseError(f"Failed to list records from {collection}: {e}") from e

    return mock_list_records


def _make_mock_get_first_record(pb: PocketBase):
    """Create mock get_first_record function."""

    async def mock_get_first_record(*, collection: str, filter_query: str) -> dict | None:
        try:
            result = pb.collection(collection).get_first_list_item(filter_query)
            return result.__dict__
        except Exception as e:
            if hasattr(e, "status") and e.status == HTTP_NOT_FOUND:
                return None
            raise DatabaseError(f"Failed to get first record from {collection}: {e}") from e

    return mock_get_first_record


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
            raise Exception(msg) from e

    async def get_record(self, *, collection: str, record_id: str) -> dict[str, Any]:
        """Get a record by ID from the specified collection."""
        try:
            record = self._pb.collection(collection).get_one(record_id)
            return record.__dict__
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                msg = f"Record not found in {collection}: {record_id}"
                raise Exception(msg) from e
            msg = f"Failed to get record from {collection}: {e}"
            raise Exception(msg) from e

    async def update_record(self, *, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a record in the specified collection."""
        try:
            record = self._pb.collection(collection).update(record_id, data)
            return record.__dict__
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                msg = f"Record not found in {collection}: {record_id}"
                raise Exception(msg) from e
            msg = f"Failed to update record in {collection}: {e}"
            raise Exception(msg) from e

    async def delete_record(self, *, collection: str, record_id: str) -> None:
        """Delete a record from the specified collection."""
        try:
            self._pb.collection(collection).delete(record_id)
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                msg = f"Record not found in {collection}: {record_id}"
                raise Exception(msg) from e
            msg = f"Failed to delete record from {collection}: {e}"
            raise Exception(msg) from e

    async def list_records(
        self,
        *,
        collection: str,
        page: int = 1,
        per_page: int = 50,
        filter_query: str = "",
        sort: str = "-created",
    ) -> list[dict[str, Any]]:
        """List records from the specified collection with filtering and pagination."""
        try:
            result = self._pb.collection(collection).get_list(
                page=page,
                per_page=per_page,
                query_params={"filter": filter_query, "sort": sort},
            )
            return [item.__dict__ for item in result.items]
        except ClientResponseError as e:
            msg = f"Failed to list records from {collection}: {e}"
            raise Exception(msg) from e

    async def get_first_record(self, *, collection: str, filter_query: str) -> dict[str, Any] | None:
        """Get the first record matching the filter query, or None if not found."""
        try:
            result = self._pb.collection(collection).get_first_list_item(filter_query)
            return result.__dict__
        except ClientResponseError as e:
            if e.status == HTTP_NOT_FOUND:
                return None
            msg = f"Failed to get first record from {collection}: {e}"
            raise Exception(msg) from e


@pytest.fixture(scope="session")
def pocketbase_server() -> Generator[str]:
    """Start ephemeral PocketBase instance for testing."""
    pb_data_dir = tempfile.mkdtemp(prefix="pb_test_")
    pb_binary = shutil.which("pocketbase")

    if pb_binary is None:
        pytest.skip("PocketBase binary not found in PATH")

    assert pb_binary is not None  # For type checker (pytest.skip already handles None case)

    process = subprocess.Popen(
        [pb_binary, "serve", "--dir", pb_data_dir, "--http", "127.0.0.1:8091"],
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
        process.kill()
        shutil.rmtree(pb_data_dir, ignore_errors=True)
        pytest.fail("PocketBase failed to start within 10 seconds")

    # Give PocketBase a moment to fully initialize
    time.sleep(1)

    # Create admin user for schema management
    try:
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
        openrouter_api_key="test_key",
        whatsapp_verify_token="test_verify",
        whatsapp_app_secret="test_secret",
        whatsapp_access_token="test_access",
        whatsapp_phone_number_id="test_phone_id",
        logfire_token="test_logfire",
        house_code="TEST123",
        house_password="testpass",
        model_id="anthropic/claude-3.5-sonnet",
    )


@pytest.fixture(scope="session")
def initialized_db(pocketbase_server: str, test_settings: Settings) -> PocketBase:
    """Initialize PocketBase schema and return authenticated client."""
    asyncio.run(sync_schema(pocketbase_url=pocketbase_server))

    # Create authenticated client for tests
    client = PocketBase(pocketbase_server)
    client.admins.auth_with_password("admin@test.local", "testpassword123")

    return client


@pytest.fixture
def mock_db_module(initialized_db: PocketBase, monkeypatch):
    """Patch the db_client module to use the test PocketBase instance."""
    # Patch all the db_client functions using helper factories
    monkeypatch.setattr(db_module, "create_record", _make_mock_create_record(initialized_db))
    monkeypatch.setattr(db_module, "get_record", _make_mock_get_record(initialized_db))
    monkeypatch.setattr(db_module, "update_record", _make_mock_update_record(initialized_db))
    monkeypatch.setattr(db_module, "delete_record", _make_mock_delete_record(initialized_db))
    monkeypatch.setattr(db_module, "list_records", _make_mock_list_records(initialized_db))
    monkeypatch.setattr(db_module, "get_first_record", _make_mock_get_first_record(initialized_db))

    yield


@pytest.fixture
def db_client(initialized_db: PocketBase) -> Generator[MockDBClient]:
    """Provide clean database for each test with async wrapper interface."""
    for collection in COLLECTIONS:
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
    admin_data = {
        "phone": phone,
        "name": name,
        "role": "admin",
        "status": "active",
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
