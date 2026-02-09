"""Integration tests for handle_join_name_step function."""

import pytest

from src.agents.choresir_agent import handle_join_name_step
from src.core.db_client import get_first_record
from src.services import session_service, user_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_success(mock_db_module, db_client) -> None:
    """Test valid name completes join flow."""
    phone = "+15550001111"
    name = "José García"
    house_name = "TestHouse"

    # Set house credentials for test (house_name is used as house_code in the flow)
    # We modify user_service.settings which is what request_join uses
    original_password = user_service.settings.house_password
    original_code = user_service.settings.house_code
    user_service.settings.house_password = "correct_password"
    user_service.settings.house_code = house_name

    try:
        # Create session in awaiting_name state
        await session_service.create_session(
            phone=phone,
            house_name=house_name,
            step="awaiting_name",
        )

        # Submit valid name
        response = await handle_join_name_step(phone, name)

        # Verify welcome message
        assert "welcome" in response.lower()
        assert name in response

        # Verify join request created in database
        user_record = await get_first_record(
            collection="members",
            filter_query=f'phone = "{phone}"',
        )
        assert user_record is not None
        assert user_record["name"] == name
        assert user_record["phone"] == phone
        assert user_record["status"] == "pending"

        # Verify session deleted
        session = await session_service.get_session(phone=phone)
        assert session is None
    finally:
        user_service.settings.house_password = original_password
        user_service.settings.house_code = original_code


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_invalid_name(mock_db_module, db_client) -> None:
    """Test invalid name returns error without deleting session."""
    phone = "+15550002222"
    invalid_name = "🎉emoji"

    # Set house password for test
    original_password = user_service.settings.house_password
    user_service.settings.house_password = "correct_password"

    try:
        # Create session in awaiting_name state
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_name",
        )

        # Submit invalid name
        response = await handle_join_name_step(phone, invalid_name)

        # Verify error message
        assert "name isn't usable" in response.lower()
        assert "letters, spaces, hyphens, and apostrophes" in response.lower()

        # Verify session still exists (not deleted)
        session = await session_service.get_session(phone=phone)
        assert session is not None
        assert session["step"] == "awaiting_name"

        # Verify no join request created
        user_record = await get_first_record(
            collection="users",
            filter_query=f'phone = "{phone}"',
        )
        assert user_record is None
    finally:
        user_service.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_unicode_names(mock_db_module, db_client) -> None:
    """Test Unicode names are accepted."""
    test_names = ["김철수", "Владимир", "O'Brien"]
    house_name = "TestHouse"

    # Set house credentials for test (house_name is used as house_code in the flow)
    original_password = user_service.settings.house_password
    original_code = user_service.settings.house_code
    user_service.settings.house_password = "correct_password"
    user_service.settings.house_code = house_name

    try:
        for i, name in enumerate(test_names):
            phone = f"+1555000{3333 + i}"

            # Create session in awaiting_name state
            await session_service.create_session(
                phone=phone,
                house_name=house_name,
                step="awaiting_name",
            )

            # Submit name
            response = await handle_join_name_step(phone, name)

            # Verify welcome message
            assert "welcome" in response.lower()
            assert name in response

            # Verify join request created
            user_record = await get_first_record(
                collection="members",
                filter_query=f'phone = "{phone}"',
            )
            assert user_record is not None
            assert user_record["name"] == name

            # Verify session deleted
            session = await session_service.get_session(phone=phone)
            assert session is None
    finally:
        user_service.settings.house_password = original_password
        user_service.settings.house_code = original_code


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_session_expired(mock_db_module, db_client) -> None:
    """Test expired session handling."""
    phone = "+15550006666"
    name = "Valid Name"

    # Don't create a session (simulate expired/missing session)
    response = await handle_join_name_step(phone, name)

    # Verify error message
    assert "session has expired" in response.lower()
    assert "/house join" in response.lower()

    # Verify no join request created
    user_record = await get_first_record(
        collection="members",
        filter_query=f'phone = "{phone}"',
    )
    assert user_record is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_session_wrong_step(mock_db_module, db_client) -> None:
    """Test session in wrong step handling."""
    phone = "+15550007777"
    name = "Valid Name"

    # Create session in wrong step
    await session_service.create_session(
        phone=phone,
        house_name="TestHouse",
        step="awaiting_password",
    )

    response = await handle_join_name_step(phone, name)

    # Verify error message
    assert "something went wrong" in response.lower()
    assert "/house join" in response.lower()

    # Verify no join request created
    user_record = await get_first_record(
        collection="members",
        filter_query=f'phone = "{phone}"',
    )
    assert user_record is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_empty_name(mock_db_module, db_client) -> None:
    """Test empty name is rejected."""
    phone = "+15550008888"
    empty_name = "   "

    # Set house password for test
    original_password = user_service.settings.house_password
    user_service.settings.house_password = "correct_password"

    try:
        # Create session in awaiting_name state
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_name",
        )

        # Submit empty name
        response = await handle_join_name_step(phone, empty_name)

        # Verify error message
        assert "name isn't usable" in response.lower()

        # Verify session still exists (not deleted)
        session = await session_service.get_session(phone=phone)
        assert session is not None

        # Verify no join request created
        user_record = await get_first_record(
            collection="users",
            filter_query=f'phone = "{phone}"',
        )
        assert user_record is None
    finally:
        user_service.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_too_long_name(mock_db_module, db_client) -> None:
    """Test too long name is rejected."""
    phone = "+15550009999"
    long_name = "A" * 51  # Max is 50 characters

    # Set house password for test
    original_password = user_service.settings.house_password
    user_service.settings.house_password = "correct_password"

    try:
        # Create session in awaiting_name state
        await session_service.create_session(
            phone=phone,
            house_name="TestHouse",
            step="awaiting_name",
        )

        # Submit too long name
        response = await handle_join_name_step(phone, long_name)

        # Verify error message
        assert "name isn't usable" in response.lower()

        # Verify session still exists (not deleted)
        session = await session_service.get_session(phone=phone)
        assert session is not None

        # Verify no join request created
        user_record = await get_first_record(
            collection="members",
            filter_query=f'phone = "{phone}"',
        )
        assert user_record is None
    finally:
        user_service.settings.house_password = original_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_name_step_name_with_whitespace(mock_db_module, db_client) -> None:
    """Test name with leading/trailing whitespace is trimmed and accepted."""
    phone = "+15550010000"
    name_with_spaces = "  John Doe  "
    expected_name = "John Doe"
    house_name = "TestHouse"

    # Set house credentials for test (house_name is used as house_code in the flow)
    original_password = user_service.settings.house_password
    original_code = user_service.settings.house_code
    user_service.settings.house_password = "correct_password"
    user_service.settings.house_code = house_name

    try:
        # Create session in awaiting_name state
        await session_service.create_session(
            phone=phone,
            house_name=house_name,
            step="awaiting_name",
        )

        # Submit name with whitespace
        response = await handle_join_name_step(phone, name_with_spaces)

        # Verify welcome message
        assert "welcome" in response.lower()
        assert expected_name in response

        # Verify join request created with trimmed name
        user_record = await get_first_record(
            collection="users",
            filter_query=f'phone = "{phone}"',
        )
        assert user_record is not None
        assert user_record["name"] == expected_name

        # Verify session deleted
        session = await session_service.get_session(phone=phone)
        assert session is None
    finally:
        user_service.settings.house_password = original_password
        user_service.settings.house_code = original_code
