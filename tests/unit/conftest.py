"""Pytest configuration and fixtures for unit tests."""

import copy
from datetime import UTC, datetime

import pytest

from src.interface.whatsapp_sender import SendMessageResult
from tests.unit.mocks import InMemoryDBClient


@pytest.fixture
def in_memory_db():
    """Provides a fresh InMemoryDBClient for each test."""
    return InMemoryDBClient()


class InMemoryDBClientAsPocketBase:
    """Wrapper that makes InMemoryDBClient compatible with PocketBase interface.

    This allows tests that expect a PocketBase object to use the in-memory
    implementation for real DB interactions without requiring an actual
    PocketBase server.
    """

    def __init__(self, in_memory_db: InMemoryDBClient):
        self._in_memory_db = in_memory_db
        self._collection_name: str = ""
        self._last_record: dict | None = None
        self._last_records: list[dict] = []

    def collection(self, collection_name: str) -> "InMemoryDBClientAsPocketBase":
        """Return self to chain collection calls."""
        self._collection_name = collection_name
        return self

    def create(self, data: dict) -> "InMemoryDBClientAsPocketBase":
        """Create record in the current collection."""
        collection = self._in_memory_db._collections.setdefault(self._collection_name, {})
        record_id = str(self._in_memory_db._id_counter)
        self._in_memory_db._id_counter += 1

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        collection[record_id] = {"id": record_id, "created": now, "updated": now, **data}
        self._last_record = collection[record_id]
        return self

    def get_one(self, record_id: str) -> "InMemoryDBClientAsPocketBase":
        """Get record by ID."""
        collection = self._in_memory_db._collections.get(self._collection_name, {})
        self._last_record = copy.deepcopy(collection.get(record_id)) if record_id in collection else None
        return self

    def get_list(
        self, page: int = 1, per_page: int = 50, query_params: dict | None = None
    ) -> "InMemoryDBClientAsPocketBase":
        """List records from collection."""
        query_params = query_params or {}
        records = list(self._in_memory_db._collections.get(self._collection_name, {}).values())

        if "filter" in query_params:
            records = [r for r in records if self._in_memory_db._parse_filter(query_params["filter"], r)]

        if "sort" in query_params:
            records = self._in_memory_db._apply_sort(records, query_params["sort"])

        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        self._last_records = [copy.deepcopy(r) for r in records[start_index:end_index]]
        return self

    def get_first_list_item(self, filter_query: str) -> "InMemoryDBClientAsPocketBase":
        """Get first matching record."""
        records = self._in_memory_db._collections.get(self._collection_name, {}).values()
        if filter_query:
            records = [r for r in records if self._in_memory_db._parse_filter(filter_query, r)]

        self._last_record = copy.deepcopy(next(iter(records))) if records else None
        return self

    def update(self, record_id: str, data: dict) -> "InMemoryDBClientAsPocketBase":
        """Update record in collection."""
        record = self._in_memory_db._collections[self._collection_name][record_id]
        record.update(data)
        record["updated"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self._last_record = record
        return self

    def delete(self, record_id: str) -> "InMemoryDBClientAsPocketBase":
        """Delete record from collection."""
        del self._in_memory_db._collections[self._collection_name][record_id]
        return self

    def get_full_list(self) -> list[dict]:
        """Get all records from collection."""
        return [copy.deepcopy(r) for r in self._in_memory_db._collections.get(self._collection_name, {}).values()]

    @property
    def items(self):
        """Return records from list operation."""
        return self._last_records

    def __getattr__(self, name: str):
        """Delegate attribute access to last_record for backward compatibility."""
        if name == "id":
            return self._last_record.get("id") if self._last_record else None
        return self._last_record.get(name) if self._last_record else None

    def as_dict(self) -> dict:
        """Return last_record as dict."""
        return self._last_record if self._last_record else {}


@pytest.fixture
def pocketbase_client(in_memory_db: InMemoryDBClient):
    """Provides a PocketBase-like client backed by InMemoryDBClient.

    This fixture creates a wrapper that mimics the PocketBase interface
    but uses the in-memory implementation, allowing tests to exercise
    real DB interactions without requiring an actual PocketBase server.
    """
    return InMemoryDBClientAsPocketBase(in_memory_db)


async def _mock_send_text_message(**kwargs) -> SendMessageResult:
    """Mock WhatsApp sender that returns success instantly."""
    return SendMessageResult(success=True, message_id="mock_message_id", error=None)


async def _mock_invalidate_cache() -> None:
    """Mock cache invalidation that does nothing."""
    pass


@pytest.fixture
def patched_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient.

    Also patches external services (WhatsApp, analytics cache) to avoid
    real HTTP calls and retry delays in unit tests.
    """

    # Patch all db_client functions
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)

    # Patch WhatsApp sender to avoid real HTTP calls and retry delays
    monkeypatch.setattr(
        "src.interface.whatsapp_sender.send_text_message",
        _mock_send_text_message,
    )

    # Patch analytics service cache invalidation
    monkeypatch.setattr(
        "src.services.analytics_service.invalidate_leaderboard_cache",
        _mock_invalidate_cache,
    )

    return in_memory_db


@pytest.fixture
def sample_user_data():
    """Returns sample user data for testing."""
    return {
        "username": "testuser",
        "phone": "+1234567890",
        "email": "test@example.com",
        "password": "securepass123",
        "passwordConfirm": "securepass123",
    }


@pytest.fixture
def sample_chore_data():
    """Returns sample chore data for testing."""
    return {
        "title": "Test Chore",
        "description": "A test chore",
        "assigned_to": [],
        "frequency": "daily",
        "points": 10,
    }
