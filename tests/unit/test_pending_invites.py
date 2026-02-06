"""Tests for pending invites schema and cleanup functionality."""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.scheduler import cleanup_expired_invites


@pytest.fixture
def patched_user_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""

    # Patch all db_client functions
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)

    return in_memory_db


@pytest.fixture
async def sample_invite(patched_user_db):
    """Create a sample pending invite."""
    invite_data = {
        "phone": "+1234567890",
        "invited_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "invite_message_id": "msg_123",
    }
    return await patched_user_db.create_record("pending_invites", invite_data)


@pytest.fixture
async def old_invite(patched_user_db):
    """Create an old pending invite (10 days ago)."""
    old_date = datetime.now(UTC) - timedelta(days=10)
    invite_data = {
        "phone": "+1987654321",
        "invited_at": old_date.isoformat().replace("+00:00", "Z"),
        "invite_message_id": "msg_456",
    }
    return await patched_user_db.create_record("pending_invites", invite_data)


@pytest.mark.unit
class TestPendingInvitesSchema:
    """Tests for pending_invites collection schema."""

    @pytest.mark.asyncio
    async def test_create_invite_success(self, patched_user_db):
        """Test creating a pending invite succeeds."""
        invite_data = {
            "phone": "+1234567890",
            "invited_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "invite_message_id": "msg_123",
        }

        result = await patched_user_db.create_record("pending_invites", invite_data)

        assert result["phone"] == invite_data["phone"]
        assert result["invited_at"] == invite_data["invited_at"]
        assert result["invite_message_id"] == invite_data["invite_message_id"]
        assert "id" in result
        assert "created" in result
        assert "updated" in result

    @pytest.mark.asyncio
    async def test_create_invite_without_message_id(self, patched_user_db):
        """Test creating a pending invite without message_id succeeds."""
        invite_data = {
            "phone": "+1234567890",
            "invited_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

        result = await patched_user_db.create_record("pending_invites", invite_data)

        assert result["phone"] == invite_data["phone"]
        assert result["invited_at"] == invite_data["invited_at"]
        assert result.get("invite_message_id") is None

    @pytest.mark.asyncio
    async def test_create_duplicate_phone_in_memory_db(self, patched_user_db, sample_invite):
        """Test creating invite with duplicate phone in memory DB."""
        new_invite_data = {
            "phone": sample_invite["phone"],
            "invited_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "invite_message_id": "msg_new",
        }

        result = await patched_user_db.create_record("pending_invites", new_invite_data)

        # In InMemoryDB, this creates a new record with unique ID
        # (PocketBase would enforce uniqueness at DB level)
        assert result["phone"] == sample_invite["phone"]
        assert result["invite_message_id"] == "msg_new"

    @pytest.mark.asyncio
    async def test_get_invite_by_phone(self, patched_user_db, sample_invite):
        """Test retrieving invite by phone number."""
        filter_query = f'phone = "{sample_invite["phone"]}"'
        result = await patched_user_db.get_first_record("pending_invites", filter_query)

        assert result is not None
        assert result["id"] == sample_invite["id"]
        assert result["phone"] == sample_invite["phone"]

    @pytest.mark.asyncio
    async def test_list_all_invites(self, patched_user_db, sample_invite, old_invite):
        """Test listing all pending invites."""
        result = await patched_user_db.list_records("pending_invites")

        assert len(result) == 2
        phones = [r["phone"] for r in result]
        assert sample_invite["phone"] in phones
        assert old_invite["phone"] in phones

    @pytest.mark.asyncio
    async def test_delete_invite(self, patched_user_db, sample_invite):
        """Test deleting a pending invite."""
        await patched_user_db.delete_record("pending_invites", sample_invite["id"])

        result = await patched_user_db.list_records("pending_invites")
        assert len(result) == 0


@pytest.mark.unit
class TestCleanupExpiredInvites:
    """Tests for cleanup_expired_invites job."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_invites(self, patched_user_db, sample_invite, old_invite):
        """Test cleanup removes invites older than 7 days."""
        await cleanup_expired_invites()

        result = await patched_user_db.list_records("pending_invites")
        assert len(result) == 1
        assert result[0]["phone"] == sample_invite["phone"]

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_invites(self, patched_user_db, sample_invite):
        """Test cleanup preserves invites younger than 7 days."""
        await cleanup_expired_invites()

        result = await patched_user_db.list_records("pending_invites")
        assert len(result) == 1
        assert result[0]["phone"] == sample_invite["phone"]

    @pytest.mark.asyncio
    async def test_cleanup_handles_empty_collection(self, patched_user_db):
        """Test cleanup handles empty collection gracefully."""
        await cleanup_expired_invites()

        result = await patched_user_db.list_records("pending_invites")
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_cleanup_removes_multiple_old_invites(self, patched_user_db):
        """Test cleanup removes multiple old invites."""
        # Create 3 old invites
        old_date = datetime.now(UTC) - timedelta(days=10)
        for i in range(3):
            await patched_user_db.create_record(
                "pending_invites",
                {
                    "phone": f"+{1234567890 + i}",
                    "invited_at": old_date.isoformat().replace("+00:00", "Z"),
                },
            )

        await cleanup_expired_invites()

        result = await patched_user_db.list_records("pending_invites")
        assert len(result) == 0
