"""Tests for handle_unknown_user function."""

import unittest.mock

import pytest

from src.agents import choresir_agent


@pytest.mark.asyncio
async def test_parse_join_request_success():
    """Test parsing a valid join request message."""
    message = "I want to join. Code: HOUSE123, Password: SecretPass, Name: Jack"
    user_phone = "+1234567890"

    # Mock user_service.request_join
    with unittest.mock.patch("src.services.user_service.request_join") as mock_join:
        mock_join.return_value = None  # Successful join

        result = await choresir_agent.handle_unknown_user(user_phone=user_phone, message_text=message)

        # Should call user_service.request_join with correct params
        mock_join.assert_called_once_with(phone=user_phone, name="Jack", house_code="HOUSE123", password="SecretPass")

        # Should return success message
        assert "Welcome, Jack!" in result
        assert "membership request has been submitted" in result


@pytest.mark.asyncio
async def test_parse_join_request_invalid_credentials():
    """Test parsing a join request with invalid credentials."""
    message = "I want to join. Code: WRONGCODE, Password: WrongPass, Name: Jack"
    user_phone = "+1234567890"

    # Mock user_service.request_join to raise ValueError
    with unittest.mock.patch("src.services.user_service.request_join") as mock_join:
        mock_join.side_effect = ValueError("Invalid house code or password")

        result = await choresir_agent.handle_unknown_user(user_phone=user_phone, message_text=message)

        # Should return error message
        assert "Sorry, I couldn't process your join request" in result
        assert "Invalid house code or password" in result


@pytest.mark.asyncio
async def test_no_join_request_returns_onboarding():
    """Test that a message without join request returns onboarding prompt."""
    message = "Hello, how do I join?"
    user_phone = "+1234567890"

    result = await choresir_agent.handle_unknown_user(user_phone=user_phone, message_text=message)

    # Should return onboarding prompt with new conversational flow
    assert "Welcome! You're not yet a member" in result
    assert "/house join" in result
    assert "I'll guide you through the rest step by step" in result


@pytest.mark.asyncio
async def test_parse_join_request_variations():
    """Test parsing join requests with various formatting."""
    test_cases = [
        "Code: ABC123, Password: Pass123, Name: John Doe",
        "code:ABC123 password:Pass123 name:John Doe",
        "I'd like to join! Code: ABC123, Password: Pass123, Name: John Doe",
        "Code:ABC123,Password:Pass123,Name:John Doe",
    ]

    for message in test_cases:
        with unittest.mock.patch("src.services.user_service.request_join") as mock_join:
            mock_join.return_value = None

            result = await choresir_agent.handle_unknown_user(user_phone="+1234567890", message_text=message)

            # Should successfully parse and process
            assert "Welcome" in result
            mock_join.assert_called_once()
