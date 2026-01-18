"""Pytest configuration and fixtures for integration tests."""

import asyncio
import logging
import shutil
import subprocess
import tempfile
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from pocketbase import PocketBase

from src.core import admin_notifier as admin_notifier_module, config as config_module, db_client as db_module
from src.core.config import Settings
from src.core.schema import COLLECTIONS, sync_schema
from src.services import user_service as user_service_module
from tests.conftest import MockDBClient


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
            raise RuntimeError(f"Failed to create record in {collection}: {e}") from e

    return mock_create_record


def _make_mock_get_record(pb: PocketBase):
    """Create mock get_record function."""

    async def mock_get_record(*, collection: str, record_id: str) -> dict:
        try:
            record = pb.collection(collection).get_one(record_id)
            return record.__dict__
        except Exception as e:
            if hasattr(e, "status") and e.status == HTTP_NOT_FOUND:
                raise KeyError(f"Record not found in {collection}: {record_id}") from e
            raise RuntimeError(f"Failed to get record from {collection}: {e}") from e

    return mock_get_record


def _make_mock_update_record(pb: PocketBase):
    """Create mock update_record function."""

    async def mock_update_record(*, collection: str, record_id: str, data: dict) -> dict:
        try:
            record = pb.collection(collection).update(record_id, data)
            return record.__dict__
        except Exception as e:
            if hasattr(e, "status") and e.status == HTTP_NOT_FOUND:
                raise KeyError(f"Record not found in {collection}: {record_id}") from e
            raise RuntimeError(f"Failed to update record in {collection}: {e}") from e

    return mock_update_record


def _make_mock_delete_record(pb: PocketBase):
    """Create mock delete_record function."""

    async def mock_delete_record(*, collection: str, record_id: str) -> None:
        try:
            pb.collection(collection).delete(record_id)
        except Exception as e:
            if hasattr(e, "status") and e.status == HTTP_NOT_FOUND:
                raise KeyError(f"Record not found in {collection}: {record_id}") from e
            raise RuntimeError(f"Failed to delete record from {collection}: {e}") from e

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
            raise RuntimeError(f"Failed to list records from {collection}: {e}") from e

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
            raise RuntimeError(f"Failed to get first record from {collection}: {e}") from e

    return mock_get_first_record


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
        twilio_account_sid="test_account_sid",
        twilio_auth_token="test_auth_token",
        twilio_whatsapp_number="whatsapp:+14155238886",
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
def mock_db_module(initialized_db: PocketBase, test_settings: Settings, monkeypatch):
    """Patch the db_client module to use the test PocketBase instance."""
    # Patch all the db_client functions using helper factories
    mock_list_records = _make_mock_list_records(initialized_db)
    monkeypatch.setattr(db_module, "create_record", _make_mock_create_record(initialized_db))
    monkeypatch.setattr(db_module, "get_record", _make_mock_get_record(initialized_db))
    monkeypatch.setattr(db_module, "update_record", _make_mock_update_record(initialized_db))
    monkeypatch.setattr(db_module, "delete_record", _make_mock_delete_record(initialized_db))
    monkeypatch.setattr(db_module, "list_records", mock_list_records)
    monkeypatch.setattr(db_module, "get_first_record", _make_mock_get_first_record(initialized_db))

    # Patch get_client to return the already-authenticated test PocketBase instance
    def mock_get_client() -> PocketBase:
        return initialized_db

    monkeypatch.setattr(db_module, "get_client", mock_get_client)

    # Patch admin_notifier's imported list_records to use the same mock
    monkeypatch.setattr(admin_notifier_module, "list_records", mock_list_records)

    # Patch the global settings to use test settings
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(db_module, "settings", test_settings)
    monkeypatch.setattr(user_service_module, "settings", test_settings)
    monkeypatch.setattr(admin_notifier_module, "settings", test_settings)

    yield


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
def clean_db(db_client: MockDBClient) -> Generator[MockDBClient]:
    """Ensure clean database state, failing loudly on cleanup errors."""
    yield db_client

    # Cleanup after test
    collections = ["verifications", "chores", "users", "conflicts"]
    cleanup_errors = []

    for collection in collections:
        try:
            # Use asyncio.run to call async method
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


@pytest.fixture
async def sample_users(db_client: MockDBClient) -> dict[str, dict]:
    """Create sample users using MockDBClient for consistency."""
    users_data = [
        {
            "username": "alice",
            "email": "alice@example.com",
            "phone": "+1234567890",
            "password": "password123",
            "passwordConfirm": "password123",
            "name": "Alice Admin",
            "role": "admin",
            "status": "active",
        },
        {
            "username": "bob",
            "email": "bob@example.com",
            "phone": "+1234567891",
            "password": "password123",
            "passwordConfirm": "password123",
            "name": "Bob Member",
            "role": "member",
            "status": "active",
        },
        {
            "username": "charlie",
            "email": "charlie@example.com",
            "phone": "+1234567892",
            "password": "password123",
            "passwordConfirm": "password123",
            "name": "Charlie Member",
            "role": "member",
            "status": "active",
        },
    ]

    created_users = {}
    for user_data in users_data:
        user = await db_client.create_record(collection="users", data=user_data)
        created_users[user_data["username"]] = user

    return created_users


@pytest.fixture
async def sample_chores(db_client: MockDBClient, sample_users: dict[str, dict]) -> list[dict]:
    """Create sample chores using MockDBClient for consistency."""
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
        chore = await db_client.create_record(collection="chores", data=chore_data)
        created_chores.append(chore)

    return created_chores
