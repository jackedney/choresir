"""Integration tests for choresir agent handle_unknown_user function."""

import pytest

from src.agents.choresir_agent import handle_unknown_user
from src.core import db_client
from src.domain.create_models import InviteCreate
from src.domain.user import UserStatus
from src.services import user_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_yes_confirms_invite_and_welcomes_user(clean_db) -> None:
    """Test that YES confirms invite, updates user status, deletes invite, and welcomes user."""
    # Step 1: Create pending user via join workflow
    pending_user = await user_service.request_join(
        phone="+15550001111",
        name="Pending User",
        house_code="TEST123",
        password="testpass",
    )

    assert pending_user["status"] == UserStatus.PENDING.value

    # Step 2: Create admin
    admin_data = {
        "phone": "+15550000000",
        "name": "Admin User",
        "email": "admin@test.local",
        "role": "admin",
        "status": "active",
        "password": "test_password",
        "passwordConfirm": "test_password",
    }
    await db_client.create_record(collection="users", data=admin_data)

    # Step 3: Create pending invite
    invite_data = InviteCreate(
        phone="+15550001111",
        invited_at="2024-01-01T00:00:00Z",
        invite_message_id="msg_id_123",
    )
    await db_client.create_record(
        collection="pending_invites",
        data=invite_data.model_dump(exclude_none=True),
    )

    # Step 4: Handle YES message
    result = await handle_unknown_user(user_phone="+15550001111", message_text="YES")

    # Verify user status was updated to active
    updated_user = await db_client.get_first_record(
        collection="users",
        filter_query='phone = "+15550001111"',
    )
    assert updated_user is not None
    assert updated_user["status"] == UserStatus.ACTIVE.value

    # Verify pending invite was deleted
    deleted_invite = await db_client.get_first_record(
        collection="pending_invites",
        filter_query='phone = "+15550001111"',
    )
    assert deleted_invite is None

    # Verify welcome message
    assert "Welcome to" in result
    assert "membership is now active" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_yes_case_insensitive_confirms_invite(clean_db) -> None:
    """Test that 'yes', 'Yes', and 'YES' all confirm the invite."""
    test_messages = ["yes", "Yes", "YES", "YeS", " yEs "]

    for i, message in enumerate(test_messages):
        # Create unique user for each test case
        phone = f"+155500011{i:02d}"
        name = f"User {i}"

        # Create pending user
        await user_service.request_join(
            phone=phone,
            name=name,
            house_code="TEST123",
            password="testpass",
        )

        # Create admin
        admin_data = {
            "phone": f"+1555000{i:02d}",
            "name": f"Admin {i}",
            "email": f"admin{i}@test.local",
            "role": "admin",
            "status": "active",
            "password": "test_password",
            "passwordConfirm": "test_password",
        }
        await db_client.create_record(collection="users", data=admin_data)

        # Create pending invite
        invite_data = InviteCreate(
            phone=phone,
            invited_at="2024-01-01T00:00:00Z",
            invite_message_id=f"msg_id_{i}",
        )
        await db_client.create_record(
            collection="pending_invites",
            data=invite_data.model_dump(exclude_none=True),
        )

        # Handle message
        result = await handle_unknown_user(user_phone=phone, message_text=message)

        # Verify invite was confirmed
        updated_user = await db_client.get_first_record(
            collection="users",
            filter_query=f'phone = "{phone}"',
        )
        assert updated_user is not None
        assert updated_user["status"] == UserStatus.ACTIVE.value

        deleted_invite = await db_client.get_first_record(
            collection="pending_invites",
            filter_query=f'phone = "{phone}"',
        )
        assert deleted_invite is None
        assert "Welcome to" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_yes_message_returns_instruction(clean_db) -> None:
    """Test that non-YES messages instruct user to reply YES."""
    test_messages = ["hello", "maybe", "no", "what?", ""]

    for i, message in enumerate(test_messages):
        # Create unique user for each test case
        phone = f"+155500022{i:02d}"

        # Create pending user
        await user_service.request_join(
            phone=phone,
            name=f"User {i}",
            house_code="TEST123",
            password="testpass",
        )

        # Create admin
        admin_data = {
            "phone": f"+1555000{i:02d}",
            "name": f"Admin {i}",
            "email": f"admin{i}@test.local",
            "role": "admin",
            "status": "active",
            "password": "test_password",
            "passwordConfirm": "test_password",
        }
        await db_client.create_record(collection="users", data=admin_data)

        # Create pending invite
        invite_data = InviteCreate(
            phone=phone,
            invited_at="2024-01-01T00:00:00Z",
            invite_message_id=f"msg_id_{i}",
        )
        await db_client.create_record(
            collection="pending_invites",
            data=invite_data.model_dump(exclude_none=True),
        )

        # Handle message
        result = await handle_unknown_user(user_phone=phone, message_text=message)

        # Verify no user status update
        user = await db_client.get_first_record(
            collection="users",
            filter_query=f'phone = "{phone}"',
        )
        assert user is not None
        assert user["status"] == UserStatus.PENDING.value

        # Verify invite still exists
        invite = await db_client.get_first_record(
            collection="pending_invites",
            filter_query=f'phone = "{phone}"',
        )
        assert invite is not None

        # Verify instruction message
        assert result == "To confirm your invitation, please reply YES"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_pending_invite_returns_not_member_message(clean_db) -> None:
    """Test that users without pending invite get 'not a member' message."""
    # Handle message from user with no pending invite
    result = await handle_unknown_user(user_phone="+15550009999", message_text="hello")

    # Verify 'not a member' message
    assert "not a member of this household" in result
    assert "contact an admin to request an invite" in result

    # Verify no records were created
    user = await db_client.get_first_record(
        collection="users",
        filter_query='phone = "+15550009999"',
    )
    assert user is None

    invite = await db_client.get_first_record(
        collection="pending_invites",
        filter_query='phone = "+15550009999"',
    )
    assert invite is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pending_invite_but_no_user_record_returns_error(clean_db) -> None:
    """Test that missing user record after pending invite returns error message."""
    # Create pending invite without a user record (edge case)
    invite_data = InviteCreate(
        phone="+15550008888",
        invited_at="2024-01-01T00:00:00Z",
        invite_message_id="msg_id_8888",
    )
    await db_client.create_record(
        collection="pending_invites",
        data=invite_data.model_dump(exclude_none=True),
    )

    # Handle YES message
    result = await handle_unknown_user(user_phone="+15550008888", message_text="YES")

    # Verify error message
    assert "error processing your invite" in result
    assert "contact an admin" in result

    # Verify invite still exists (no update/delete attempted)
    invite = await db_client.get_first_record(
        collection="pending_invites",
        filter_query='phone = "+15550008888"',
    )
    assert invite is not None
