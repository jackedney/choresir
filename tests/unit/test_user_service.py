"""Unit tests for user_service module."""

import pytest

from src.core.config import settings

# KeyError replaced with KeyError
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


@pytest.fixture
def valid_join_credentials():
    """Valid house code and password for testing."""
    return {
        "house_code": "HOUSE123",
        "house_password": "secret123",
    }


@pytest.fixture
def sample_join_request(valid_join_credentials):
    """Sample join request data."""
    return {
        "phone": "+1234567890",
        "name": "Test User",
        "house_code": valid_join_credentials["house_code"],
        "password": valid_join_credentials["house_password"],
    }


@pytest.fixture
def patched_settings(monkeypatch, valid_join_credentials):
    """Patch settings with test house credentials."""
    monkeypatch.setattr(settings, "house_code", valid_join_credentials["house_code"])
    monkeypatch.setattr(settings, "house_password", valid_join_credentials["house_password"])

    return settings


@pytest.mark.unit
class TestRequestJoin:
    """Tests for request_join function."""

    async def test_request_join_success(self, patched_user_db, patched_settings, sample_join_request):
        """Test successful join request creates pending user."""
        result = await user_service.request_join(**sample_join_request)

        assert result["phone"] == sample_join_request["phone"]
        assert result["name"] == sample_join_request["name"]
        assert result["role"] == UserRole.MEMBER
        assert result["status"] == UserStatus.PENDING
        assert "id" in result
        assert "created" in result

        # Email should be generated from phone
        expected_email = f"{sample_join_request['phone'].replace('+', '').replace('-', '')}@choresir.local"
        assert result["email"] == expected_email

        # Password should be securely generated
        assert result["password"] != "temp_password_will_be_set_on_activation"
        assert len(result["password"]) >= 32  # Should be long enough
        assert result["password"] == result["passwordConfirm"]

    async def test_request_join_invalid_house_code(self, patched_user_db, patched_settings, sample_join_request):
        """Test join request fails with invalid house code."""
        sample_join_request["house_code"] = "WRONG_CODE"

        with pytest.raises(ValueError, match="Invalid house code or password"):
            await user_service.request_join(**sample_join_request)

    async def test_request_join_invalid_password(self, patched_user_db, patched_settings, sample_join_request):
        """Test join request fails with invalid password."""
        sample_join_request["password"] = "wrong_password"

        with pytest.raises(ValueError, match="Invalid house code or password"):
            await user_service.request_join(**sample_join_request)

    async def test_request_join_duplicate_phone(self, patched_user_db, patched_settings, sample_join_request):
        """Test join request fails if phone number already exists."""
        # Create first user
        await user_service.request_join(**sample_join_request)

        # Try to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            await user_service.request_join(**sample_join_request)

    async def test_request_join_invalid_name_emoji(self, patched_user_db, patched_settings, sample_join_request):
        """Test join request fails with emoji in name."""
        sample_join_request["name"] = "Test🎉User"
        with pytest.raises(ValueError, match="can only contain"):
            await user_service.request_join(**sample_join_request)

    async def test_request_join_invalid_name_special_chars(
        self, patched_user_db, patched_settings, sample_join_request
    ):
        """Test join request fails with special characters in name."""
        sample_join_request["name"] = "user@test"
        with pytest.raises(ValueError, match="can only contain"):
            await user_service.request_join(**sample_join_request)

    async def test_request_join_invalid_name_too_long(self, patched_user_db, patched_settings, sample_join_request):
        """Test join request fails with name too long."""
        sample_join_request["name"] = "a" * 51
        with pytest.raises(ValueError, match="too long"):
            await user_service.request_join(**sample_join_request)

    async def test_request_join_invalid_name_empty(self, patched_user_db, patched_settings, sample_join_request):
        """Test join request fails with empty name."""
        sample_join_request["name"] = "   "
        with pytest.raises(ValueError, match="cannot be empty"):
            await user_service.request_join(**sample_join_request)


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
        return await patched_user_db.create_record("users", admin_data)

    @pytest.fixture
    async def pending_user(self, patched_user_db):
        """Create a pending user for testing."""
        pending_data = {
            "phone": "+2222222222",
            "name": "Pending User",
            "email": "2222222222@choresir.local",
            "role": UserRole.MEMBER,
            "status": UserStatus.PENDING,
            "password": "temp_pass",
            "passwordConfirm": "temp_pass",
        }
        return await patched_user_db.create_record("users", pending_data)

    async def test_approve_member_success(self, patched_user_db, admin_user, pending_user):
        """Test admin successfully approves pending member."""
        result = await user_service.approve_member(admin_user_id=admin_user["id"], target_phone=pending_user["phone"])

        assert result["id"] == pending_user["id"]
        assert result["status"] == UserStatus.ACTIVE
        assert result["phone"] == pending_user["phone"]

    async def test_approve_member_non_admin_fails(self, patched_user_db, pending_user):
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
        member = await patched_user_db.create_record("users", member_data)

        with pytest.raises(PermissionError, match="not authorized to approve"):
            await user_service.approve_member(admin_user_id=member["id"], target_phone=pending_user["phone"])

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
        active_user = await patched_user_db.create_record("users", active_data)

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
        return await patched_user_db.create_record("users", admin_data)

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
        return await patched_user_db.create_record("users", user_data)

    async def test_remove_user_success(self, patched_user_db, admin_user, active_user):
        """Test admin successfully removes user."""
        await user_service.remove_user(admin_user_id=admin_user["id"], target_user_id=active_user["id"])

        # Verify user was deleted
        with pytest.raises(KeyError):
            await patched_user_db.get_record("users", active_user["id"])

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
        member = await patched_user_db.create_record("users", member_data)

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
        return await patched_user_db.create_record("users", user_data)

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
        return await patched_user_db.create_record("users", user_data)

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
