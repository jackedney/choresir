"""Unit tests for user_service module."""

import pytest

from src.domain.user import UserRole, UserStatus
from src.services import user_service


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


@pytest.mark.unit
class TestCreatePendingNameUser:
    """Tests for create_pending_name_user function."""

    async def test_create_pending_name_user_success(self, patched_user_db):
        """Test successfully creating a pending_name user."""
        result = await user_service.create_pending_name_user(phone="+1234567890")

        assert result["phone"] == "+1234567890"
        assert result["name"] == "Pending"
        assert result["role"] == UserRole.MEMBER
        assert result["status"] == UserStatus.PENDING_NAME
        assert "id" in result
        assert "created" in result

    async def test_create_pending_name_user_duplicate_phone(self, patched_user_db):
        """Test creating duplicate phone number fails."""
        await user_service.create_pending_name_user(phone="+1234567890")

        with pytest.raises(ValueError, match="already exists"):
            await user_service.create_pending_name_user(phone="+1234567890")


@pytest.mark.unit
class TestUpdateUserName:
    """Tests for update_user_name function."""

    @pytest.fixture
    async def pending_name_user(self, patched_user_db):
        """Create a pending_name user for testing."""
        return await user_service.create_pending_name_user(phone="+1234567890")

    async def test_update_user_name_success(self, patched_user_db, pending_name_user):
        """Test successfully updating user name."""
        result = await user_service.update_user_name(
            user_id=pending_name_user["id"],
            name="John Doe",
        )

        assert result["name"] == "John Doe"
        assert result["id"] == pending_name_user["id"]

    async def test_update_user_name_invalid_name(self, patched_user_db, pending_name_user):
        """Test updating with invalid name fails."""
        with pytest.raises(ValueError, match="can only contain"):
            await user_service.update_user_name(
                user_id=pending_name_user["id"],
                name="Test@User",
            )


@pytest.mark.unit
class TestUpdateUserStatus:
    """Tests for update_user_status function."""

    @pytest.fixture
    async def pending_name_user(self, patched_user_db):
        """Create a pending_name user for testing."""
        return await user_service.create_pending_name_user(phone="+1234567890")

    async def test_update_user_status_success(self, patched_user_db, pending_name_user):
        """Test successfully updating user status."""
        result = await user_service.update_user_status(
            user_id=pending_name_user["id"],
            status=UserStatus.ACTIVE,
        )

        assert result["status"] == UserStatus.ACTIVE
        assert result["id"] == pending_name_user["id"]


@pytest.mark.unit
class TestApproveMember:
    """Tests for approve_member function."""

    @pytest.fixture
    async def admin_user(self, patched_user_db):
        """Create an admin user for testing."""
        admin_data = {
            "phone": "+1111111111",
            "name": "Admin User",
            "email": "admin@choresir.local",
            "role": UserRole.ADMIN,
            "status": UserStatus.ACTIVE,
            "password": "admin_pass",
            "passwordConfirm": "admin_pass",
        }
        return await patched_user_db.create_record("members", admin_data)

    @pytest.fixture
    async def pending_name_user(self, patched_user_db):
        """Create a pending_name user for testing."""
        pending_data = {
            "phone": "+2222222222",
            "name": "Pending User",
            "email": "2222222222@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.PENDING_NAME,
            "password": "temp_pass",
            "passwordConfirm": "temp_pass",
        }
        return await patched_user_db.create_record("members", pending_data)

    async def test_approve_member_success(self, patched_user_db, admin_user, pending_name_user):
        """Test admin successfully approves pending_name member."""
        result = await user_service.approve_member(
            admin_user_id=admin_user["id"],
            target_phone=pending_name_user["phone"],
        )

        assert result["id"] == pending_name_user["id"]
        assert result["status"] == UserStatus.ACTIVE
        assert result["phone"] == pending_name_user["phone"]

    async def test_approve_member_non_admin_fails(self, patched_user_db, pending_name_user):
        """Test non-admin cannot approve members."""
        # Create regular member
        member_data = {
            "phone": "+3333333333",
            "name": "Regular Member",
            "email": "member@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        }
        member = await patched_user_db.create_record("members", member_data)

        with pytest.raises(PermissionError, match="not authorized to approve"):
            await user_service.approve_member(admin_user_id=member["id"], target_phone=pending_name_user["phone"])

    async def test_approve_member_user_not_found(self, patched_user_db, admin_user):
        """Test approving non-existent user raises error."""
        with pytest.raises(KeyError, match="not found"):
            await user_service.approve_member(admin_user_id=admin_user["id"], target_phone="+9999999999")

    async def test_approve_member_already_active_fails(self, patched_user_db, admin_user):
        """Test cannot approve user who is already active."""
        # Create active user
        active_data = {
            "phone": "+4444444444",
            "name": "Active User",
            "email": "active@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        }
        active_user = await patched_user_db.create_record("members", active_data)

        with pytest.raises(ValueError, match="not pending approval"):
            await user_service.approve_member(admin_user_id=admin_user["id"], target_phone=active_user["phone"])


@pytest.mark.unit
class TestRemoveUser:
    """Tests for remove_user function."""

    @pytest.fixture
    async def admin_user(self, patched_user_db):
        """Create an admin user for testing."""
        admin_data = {
            "phone": "+1111111111",
            "name": "Admin User",
            "email": "admin@choresir.local",
            "role": UserRole.ADMIN,
            "status": UserStatus.ACTIVE,
            "password": "admin_pass",
            "passwordConfirm": "admin_pass",
        }
        return await patched_user_db.create_record("members", admin_data)

    @pytest.fixture
    async def active_user(self, patched_user_db):
        """Create an active user for testing."""
        user_data = {
            "phone": "+2222222222",
            "name": "Test User",
            "email": "test@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        }
        return await patched_user_db.create_record("members", user_data)

    async def test_remove_user_success(self, patched_user_db, admin_user, active_user):
        """Test admin successfully removes user."""
        await user_service.remove_user(admin_user_id=admin_user["id"], target_user_id=active_user["id"])

        # Verify user was deleted
        with pytest.raises(KeyError):
            await patched_user_db.get_record("members", active_user["id"])

    async def test_remove_user_non_admin_fails(self, patched_user_db, active_user):
        """Test non-admin cannot remove users."""
        # Create another regular member
        member_data = {
            "phone": "+3333333333",
            "name": "Regular Member",
            "email": "member@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        }
        member = await patched_user_db.create_record("members", member_data)

        with pytest.raises(PermissionError, match="not authorized to remove"):
            await user_service.remove_user(admin_user_id=member["id"], target_user_id=active_user["id"])

    async def test_remove_user_not_found(self, patched_user_db, admin_user):
        """Test removing non-existent user raises error."""
        with pytest.raises(KeyError):
            await user_service.remove_user(admin_user_id=admin_user["id"], target_user_id="nonexistent_id")


@pytest.mark.unit
class TestGetUserByPhone:
    """Tests for get_user_by_phone function."""

    @pytest.fixture
    async def test_user(self, patched_user_db):
        """Create a test user."""
        user_data = {
            "phone": "+1234567890",
            "name": "Test User",
            "email": "test@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        }
        return await patched_user_db.create_record("members", user_data)

    async def test_get_user_by_phone_found(self, patched_user_db, test_user):
        """Test retrieving user by phone when exists."""
        result = await user_service.get_user_by_phone(phone=test_user["phone"])

        assert result is not None
        assert result["id"] == test_user["id"]
        assert result["phone"] == test_user["phone"]
        assert result["name"] == test_user["name"]

    async def test_get_user_by_phone_not_found(self, patched_user_db):
        """Test retrieving non-existent user returns None."""
        result = await user_service.get_user_by_phone(phone="+9999999999")

        assert result is None


@pytest.mark.unit
class TestGetUserById:
    """Tests for get_user_by_id function."""

    @pytest.fixture
    async def test_user(self, patched_user_db):
        """Create a test user."""
        user_data = {
            "phone": "+1234567890",
            "name": "Test User",
            "email": "test@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.ACTIVE,
            "password": "pass",
            "passwordConfirm": "pass",
        }
        return await patched_user_db.create_record("members", user_data)

    async def test_get_user_by_id_found(self, patched_user_db, test_user):
        """Test retrieving user by ID when exists."""
        result = await user_service.get_user_by_id(user_id=test_user["id"])

        assert result["id"] == test_user["id"]
        assert result["phone"] == test_user["phone"]
        assert result["name"] == test_user["name"]

    async def test_get_user_by_id_not_found(self, patched_user_db):
        """Test retrieving non-existent user raises KeyError."""
        with pytest.raises(KeyError):
            await user_service.get_user_by_id(user_id="nonexistent_id")
