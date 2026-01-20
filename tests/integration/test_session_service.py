"""Integration tests for session service."""

from datetime import UTC, datetime, timedelta

import pytest

from src.services import session_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_session_replaces_existing(mock_db_module, db_client) -> None:
    """Test that creating a session replaces any existing session."""
    phone = "+15550001111"

    # Create first session
    session1 = await session_service.create_session(
        phone=phone,
        house_name="FirstHouse",
        step="awaiting_password",
    )

    assert session1["phone"] == phone
    assert session1["house_name"] == "FirstHouse"
    assert session1["step"] == "awaiting_password"
    assert session1["password_attempts_count"] == 0

    # Create second session for same phone
    session2 = await session_service.create_session(
        phone=phone,
        house_name="SecondHouse",
        step="awaiting_name",
    )

    assert session2["phone"] == phone
    assert session2["house_name"] == "SecondHouse"
    assert session2["step"] == "awaiting_name"

    # Verify only second session exists
    retrieved_session = await session_service.get_session(phone=phone)
    assert retrieved_session is not None
    assert retrieved_session["house_name"] == "SecondHouse"
    assert retrieved_session["step"] == "awaiting_name"

    # Verify first session was deleted by checking DB directly
    all_sessions = await db_client.list_records(
        collection="join_sessions",
        filter_query=f'phone = "{phone}"',
    )
    assert len(all_sessions) == 1
    assert all_sessions[0]["id"] == session2["id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_session_returns_none_when_expired(mock_db_module, db_client) -> None:
    """Test that expired sessions are deleted and None is returned."""
    phone = "+15550002222"

    # Create session
    session = await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )

    assert session["phone"] == phone

    # Manually set expires_at to past time
    past_time = datetime.now() - timedelta(minutes=1)
    await db_client.update_record(
        collection="join_sessions",
        record_id=session["id"],
        data={"expires_at": past_time.isoformat()},
    )

    # Call get_session - should return None and delete the session
    retrieved_session = await session_service.get_session(phone=phone)
    assert retrieved_session is None

    # Verify session was deleted
    all_sessions = await db_client.list_records(
        collection="join_sessions",
        filter_query=f'phone = "{phone}"',
    )
    assert len(all_sessions) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_session_returns_active_session(mock_db_module, db_client) -> None:
    """Test that get_session returns an active session."""
    phone = "+15550003333"

    # Create session
    await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )

    # Retrieve session
    retrieved_session = await session_service.get_session(phone=phone)
    assert retrieved_session is not None
    assert retrieved_session["phone"] == phone
    assert retrieved_session["house_name"] == "TestHouse"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_session(mock_db_module, db_client) -> None:
    """Test updating session fields."""
    phone = "+15550004444"

    # Create session
    await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
        step="awaiting_password",
    )

    # Update session
    result = await session_service.update_session(
        phone=phone,
        updates={"step": "awaiting_name"},
    )
    assert result is True

    # Verify update
    updated_session = await session_service.get_session(phone=phone)
    assert updated_session is not None
    assert updated_session["step"] == "awaiting_name"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_nonexistent_session(mock_db_module, db_client) -> None:
    """Test updating a nonexistent session returns False."""
    phone = "+15550005555"

    result = await session_service.update_session(
        phone=phone,
        updates={"step": "awaiting_name"},
    )
    assert result is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_session(mock_db_module, db_client) -> None:
    """Test deleting a session."""
    phone = "+15550006666"

    # Create session
    await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )

    # Delete session
    result = await session_service.delete_session(phone=phone)
    assert result is True

    # Verify deletion
    retrieved_session = await session_service.get_session(phone=phone)
    assert retrieved_session is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_nonexistent_session(mock_db_module, db_client) -> None:
    """Test deleting a nonexistent session returns False."""
    phone = "+15550007777"

    result = await session_service.delete_session(phone=phone)
    assert result is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_is_rate_limited(mock_db_module, db_client) -> None:
    """Test rate limiting logic."""
    phone = "+15550008888"

    # Create session
    session = await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )

    # Set last_attempt_at to now
    now = datetime.now()
    await db_client.update_record(
        collection="join_sessions",
        record_id=session["id"],
        data={"last_attempt_at": now.isoformat()},
    )

    # Retrieve session and check rate limit
    updated_session = await session_service.get_session(phone=phone)
    assert updated_session is not None
    is_limited = session_service.is_rate_limited(session=updated_session)
    assert is_limited is True

    # Set last_attempt_at to 6 seconds ago
    six_seconds_ago = now - timedelta(seconds=6)
    await db_client.update_record(
        collection="join_sessions",
        record_id=session["id"],
        data={"last_attempt_at": six_seconds_ago.isoformat()},
    )

    # Check rate limit again
    updated_session = await session_service.get_session(phone=phone)
    assert updated_session is not None
    is_limited = session_service.is_rate_limited(session=updated_session)
    assert is_limited is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_is_rate_limited_no_last_attempt(mock_db_module, db_client) -> None:
    """Test rate limiting returns False when last_attempt_at is not set."""
    phone = "+15550009999"

    # Create session
    await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )

    # Check rate limit without any attempts
    retrieved_session = await session_service.get_session(phone=phone)
    assert retrieved_session is not None
    is_limited = session_service.is_rate_limited(session=retrieved_session)
    assert is_limited is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_increment_password_attempts(mock_db_module, db_client) -> None:
    """Test password attempt tracking."""
    phone = "+15550010000"

    # Create session (count = 0)
    session = await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )

    assert session["password_attempts_count"] == 0
    # PocketBase returns empty string for unset optional date fields
    assert not session.get("last_attempt_at")

    # Increment attempts
    await session_service.increment_password_attempts(phone=phone)

    # Verify count = 1 and last_attempt_at is set
    updated_session = await session_service.get_session(phone=phone)
    assert updated_session is not None
    assert updated_session["password_attempts_count"] == 1
    assert updated_session["last_attempt_at"] is not None

    # Increment again
    await session_service.increment_password_attempts(phone=phone)

    # Verify count = 2
    updated_session = await session_service.get_session(phone=phone)
    assert updated_session is not None
    assert updated_session["password_attempts_count"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_increment_password_attempts_nonexistent_session(mock_db_module, db_client) -> None:
    """Test incrementing attempts for nonexistent session doesn't raise error."""
    phone = "+15550011111"

    # Should not raise an error
    await session_service.increment_password_attempts(phone=phone)

    # Verify no session was created
    session = await session_service.get_session(phone=phone)
    assert session is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_expiry_calculation(mock_db_module, db_client) -> None:
    """Test that session expiry is calculated correctly."""
    phone = "+15550012222"

    # Create session
    before_create = datetime.now()
    session = await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )
    after_create = datetime.now()

    # Parse timestamps
    created_at = datetime.fromisoformat(session["created_at"].replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))

    # Verify created_at is within expected range (with small tolerance for timing variance)
    tolerance = timedelta(milliseconds=100)  # 100ms tolerance for timing variance
    before_with_tz = before_create.replace(tzinfo=created_at.tzinfo) - tolerance
    after_with_tz = after_create.replace(tzinfo=created_at.tzinfo) + tolerance
    assert before_with_tz <= created_at <= after_with_tz

    # Verify expires_at is 5 minutes after created_at
    expected_expiry = created_at + timedelta(minutes=5)
    time_diff = abs((expires_at - expected_expiry).total_seconds())
    assert time_diff < 1  # Allow 1 second tolerance


@pytest.mark.integration
@pytest.mark.asyncio
async def test_is_expired_function(mock_db_module, db_client) -> None:
    """Test the is_expired function."""
    phone = "+15550013333"

    # Create session
    session = await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
    )

    # Active session should not be expired
    assert session_service.is_expired(session) is False

    # Set expires_at to past time
    past_time = datetime.now(UTC) - timedelta(minutes=1)
    session["expires_at"] = past_time.isoformat()

    # Expired session should be expired
    assert session_service.is_expired(session) is True

    # Set expires_at to future time
    future_time = datetime.now(UTC) + timedelta(minutes=10)
    session["expires_at"] = future_time.isoformat()

    # Future session should not be expired
    assert session_service.is_expired(session) is False
