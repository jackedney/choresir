"""Integration tests for handle_house_join command handler."""

import pytest

from src.agents import choresir_agent
from src.agents.choresir_agent import handle_house_join
from src.core import db_client as db
from src.domain.user import UserStatus
from src.services import session_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_house_join_success(mock_db_module, db_client) -> None:
    """Test successful join command initiation."""
    phone = "+15550001111"
    house_name = choresir_agent.settings.house_name or "TestHouse"

    # Temporarily set house_name for test
    original_house_name = choresir_agent.settings.house_name
    choresir_agent.settings.house_name = house_name

    try:
        response = await handle_house_join(phone, house_name)

        # Verify password prompt
        assert "password" in response.lower()

        # Verify session created in database
        session = await session_service.get_session(phone=phone)
        assert session is not None
        assert session["phone"] == phone
        assert session["house_name"] == house_name
        assert session["step"] == "awaiting_password"
        assert session["password_attempts_count"] == 0
    finally:
        # Restore original setting
        choresir_agent.settings.house_name = original_house_name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_house_join_invalid_house_name(mock_db_module, db_client) -> None:
    """Test invalid house name rejection."""
    phone = "+15550002222"

    # Set a house name for testing
    original_house_name = choresir_agent.settings.house_name
    choresir_agent.settings.house_name = "CorrectHouse"

    try:
        response = await handle_house_join(phone, "WrongHouse")

        # Verify error message
        assert "invalid house name" in response.lower()

        # Verify no session created
        session = await session_service.get_session(phone=phone)
        assert session is None
    finally:
        choresir_agent.settings.house_name = original_house_name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_house_join_already_member(mock_db_module, db_client) -> None:
    """Test already-member check."""
    phone = "+15550003333"
    house_name = choresir_agent.settings.house_name or "TestHouse"

    # Set house name for test
    original_house_name = choresir_agent.settings.house_name
    choresir_agent.settings.house_name = house_name

    try:
        # Create an active user in database
        user_data = {
            "phone": phone,
            "name": "Test User",
            "email": f"{phone.replace('+', '').replace('-', '')}@test.local",
            "role": "member",
            "status": UserStatus.ACTIVE,
            "password": "test_password",
            "passwordConfirm": "test_password",
        }
        await db.create_record(collection="users", data=user_data)

        # Try to join
        response = await handle_house_join(phone, house_name)

        # Verify already-member message
        assert "already a member" in response.lower()

        # Verify no session created
        session = await session_service.get_session(phone=phone)
        assert session is None
    finally:
        choresir_agent.settings.house_name = original_house_name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_house_join_case_insensitive(mock_db_module, db_client) -> None:
    """Test case-insensitive house name matching."""
    phone = "+15550004444"

    # Set house name for test
    original_house_name = choresir_agent.settings.house_name
    choresir_agent.settings.house_name = "MyHouse"

    try:
        # Test with lowercase
        response = await handle_house_join(phone, "myhouse")

        # Should succeed with lowercase house name
        assert "password" in response.lower()

        # Verify session created
        session = await session_service.get_session(phone=phone)
        assert session is not None
        assert session["house_name"] == "myhouse"  # Stored as provided
        assert session["step"] == "awaiting_password"

        # Clean up session
        await session_service.delete_session(phone=phone)

        # Test with uppercase
        response = await handle_house_join(phone, "MYHOUSE")
        assert "password" in response.lower()

        session = await session_service.get_session(phone=phone)
        assert session is not None
        assert session["house_name"] == "MYHOUSE"

        # Clean up session
        await session_service.delete_session(phone=phone)

        # Test with mixed case
        response = await handle_house_join(phone, "MyHoUsE")
        assert "password" in response.lower()

        session = await session_service.get_session(phone=phone)
        assert session is not None
    finally:
        choresir_agent.settings.house_name = original_house_name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_house_join_replaces_existing_session(mock_db_module, db_client) -> None:
    """Test that new join command replaces existing session."""
    phone = "+15550005555"
    house_name = choresir_agent.settings.house_name or "TestHouse"

    # Set house name for test
    original_house_name = choresir_agent.settings.house_name
    choresir_agent.settings.house_name = house_name

    try:
        # Create first session
        response1 = await handle_house_join(phone, house_name)
        assert "password" in response1.lower()

        session1 = await session_service.get_session(phone=phone)
        assert session1 is not None
        session1_id = session1["id"]

        # Create second session (should replace first)
        response2 = await handle_house_join(phone, house_name)
        assert "password" in response2.lower()

        session2 = await session_service.get_session(phone=phone)
        assert session2 is not None
        assert session2["id"] != session1_id  # Different session
    finally:
        choresir_agent.settings.house_name = original_house_name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_house_join_no_house_name_configured(mock_db_module, db_client) -> None:
    """Test error handling when house name is not configured."""
    phone = "+15550006666"

    # Temporarily unset house_name
    original_house_name = choresir_agent.settings.house_name
    choresir_agent.settings.house_name = None

    try:
        response = await handle_house_join(phone, "AnyHouse")

        # Should return error message about service not available
        assert "not available" in response.lower() or "administrator" in response.lower()

        # Verify no session created
        session = await session_service.get_session(phone=phone)
        assert session is None
    finally:
        choresir_agent.settings.house_name = original_house_name
