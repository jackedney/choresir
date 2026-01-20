"""Integration tests for handle_join_password_step function."""

from datetime import UTC, datetime, timedelta

import pytest

from src.agents import choresir_agent
from src.agents.choresir_agent import handle_join_password_step
from src.services import session_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_success(mock_db_module, db_client) -> None:
    """Test valid password advances to name step."""
    phone = "+15550001111"

    # Set house password for test
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = "correct_password"

    try:
        # Create session in awaiting_password state
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_password",
        )

        # Submit correct password
        response = await handle_join_password_step(phone, "correct_password")

        # Verify security reminder and name prompt
        assert "delete your previous message" in response.lower()
        assert "name would you like" in response.lower()

        # Verify session updated to awaiting_name
        session = await session_service.get_session(phone=phone)
        assert session is not None
        assert session["step"] == "awaiting_name"
    finally:
        choresir_agent.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_invalid(mock_db_module, db_client) -> None:
    """Test invalid password returns error."""
    phone = "+15550002222"

    # Set house password for test
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = "correct_password"

    try:
        # Create session
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_password",
        )

        # Get initial session state
        initial_session = await session_service.get_session(phone=phone)
        assert initial_session is not None
        assert initial_session["password_attempts_count"] == 0

        # Submit wrong password
        response = await handle_join_password_step(phone, "wrong_password")

        # Verify error message
        assert "invalid password" in response.lower()
        assert "try again" in response.lower()

        # Verify attempt counter incremented
        updated_session = await session_service.get_session(phone=phone)
        assert updated_session is not None
        assert updated_session["password_attempts_count"] == 1
        assert updated_session["last_attempt_at"] is not None

        # Verify session still in awaiting_password state
        assert updated_session["step"] == "awaiting_password"
    finally:
        choresir_agent.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_rate_limited(mock_db_module, db_client) -> None:
    """Test rate limiting enforcement."""
    phone = "+15550003333"

    # Set house password for test
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = "correct_password"

    try:
        # Create session with recent last_attempt_at
        session = await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_password",
        )

        # Set last_attempt_at to now (within rate limit window)
        await db_client.update_record(
            collection="join_sessions",
            record_id=session["id"],
            data={"last_attempt_at": datetime.now().isoformat()},
        )

        # Try to submit password while rate limited
        response = await handle_join_password_step(phone, "any_password")

        # Verify rate limit message
        assert "wait a few seconds" in response.lower()

        # Verify attempt counter NOT incremented (rate limited)
        updated_session = await session_service.get_session(phone=phone)
        assert updated_session is not None
        assert updated_session["password_attempts_count"] == 0
    finally:
        choresir_agent.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_session_expired(mock_db_module, db_client) -> None:
    """Test expired session handling."""
    phone = "+15550004444"

    # Set house password for test
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = "correct_password"

    try:
        # Create session
        session = await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_password",
        )

        # Manually expire the session
        past_time = datetime.now() - timedelta(minutes=1)
        await db_client.update_record(
            collection="join_sessions",
            record_id=session["id"],
            data={"expires_at": past_time.isoformat()},
        )

        # Try to submit password with expired session
        response = await handle_join_password_step(phone, "correct_password")

        # Verify expired session message
        assert "session has expired" in response.lower()
        assert "/house join" in response.lower()

        # Verify session was deleted (get_session returns None for expired)
        retrieved_session = await session_service.get_session(phone=phone)
        assert retrieved_session is None
    finally:
        choresir_agent.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_no_session(mock_db_module, db_client) -> None:
    """Test handling when no session exists."""
    phone = "+15550005555"

    # Set house password for test
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = "correct_password"

    try:
        # Try to submit password without a session
        response = await handle_join_password_step(phone, "correct_password")

        # Verify error message
        assert "session has expired" in response.lower()
    finally:
        choresir_agent.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_multiple_failed_attempts(mock_db_module, db_client) -> None:
    """Test multiple failed password attempts."""
    phone = "+15550006666"

    # Set house password for test
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = "correct_password"

    try:
        # Create session
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_password",
        )

        # First failed attempt
        response1 = await handle_join_password_step(phone, "wrong1")
        assert "invalid password" in response1.lower()

        session1 = await session_service.get_session(phone=phone)
        assert session1 is not None
        assert session1["password_attempts_count"] == 1

        # Clear rate limiting by setting last_attempt_at to the past
        past_time = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        await db_client.update_record(
            collection="join_sessions",
            record_id=session1["id"],
            data={"last_attempt_at": past_time},
        )

        # Second failed attempt
        response2 = await handle_join_password_step(phone, "wrong2")
        assert "invalid password" in response2.lower()

        session2 = await session_service.get_session(phone=phone)
        assert session2 is not None
        assert session2["password_attempts_count"] == 2

        # Clear rate limiting by setting last_attempt_at to the past
        past_time = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        await db_client.update_record(
            collection="join_sessions",
            record_id=session2["id"],
            data={"last_attempt_at": past_time},
        )

        # Third failed attempt
        response3 = await handle_join_password_step(phone, "wrong3")
        assert "invalid password" in response3.lower()

        session3 = await session_service.get_session(phone=phone)
        assert session3 is not None
        assert session3["password_attempts_count"] == 3
    finally:
        choresir_agent.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_success_after_failed_attempts(mock_db_module, db_client) -> None:
    """Test successful password entry after failed attempts."""
    phone = "+15550007777"

    # Set house password for test
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = "correct_password"

    try:
        # Create session
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_password",
        )

        # Failed attempt
        response1 = await handle_join_password_step(phone, "wrong")
        assert "invalid password" in response1.lower()

        # Clear rate limiting by setting last_attempt_at to the past
        session1 = await session_service.get_session(phone=phone)
        assert session1 is not None
        past_time = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        await db_client.update_record(
            collection="join_sessions",
            record_id=session1["id"],
            data={"last_attempt_at": past_time},
        )

        # Successful attempt
        response2 = await handle_join_password_step(phone, "correct_password")
        assert "delete your previous message" in response2.lower()
        assert "name would you like" in response2.lower()

        # Verify session advanced to next step
        session = await session_service.get_session(phone=phone)
        assert session is not None
        assert session["step"] == "awaiting_name"
    finally:
        choresir_agent.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_step_no_password_configured(mock_db_module, db_client) -> None:
    """Test error handling when house password is not configured."""
    phone = "+15550008888"

    # Temporarily unset house_password
    original_password = choresir_agent.settings.house_password
    choresir_agent.settings.house_password = None

    try:
        # Create session
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_password",
        )

        # Try to submit password without configured password
        response = await handle_join_password_step(phone, "any_password")

        # Verify error message
        assert "not available" in response.lower() or "administrator" in response.lower()
    finally:
        choresir_agent.settings.house_password = original_password
