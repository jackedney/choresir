"""Integration tests for admin error notifications."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import choresir_agent
from src.agents.base import Deps
from src.interface import webhook
from src.interface.whatsapp_parser import ParsedMessage


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quota_exceeded_notification_to_admin(mock_db_module, db_client, sample_users: dict) -> None:
    """Test that admin receives notification when OpenRouter quota is exceeded."""
    # Use alice from sample_users as admin (role="admin" in integration/conftest.py)
    admin = sample_users["alice"]

    # Use bob from sample_users as regular user
    user = sample_users["bob"]

    # Create test deps
    deps = Deps(
        db=None,  # SQLite - no db client object needed
        user_id=user["id"],
        user_phone=user["phone"],
        user_name=user["name"],
        user_role=user["role"],
        current_time=datetime.now(),
    )

    # Mock the agent to raise a quota exceeded error
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=Exception("OpenRouter quota exceeded: insufficient credits"))

    # Mock send_text_message to capture admin notification
    sent_messages = []

    async def mock_send_message(to_phone: str, text: str):
        sent_messages.append({"to_phone": to_phone, "text": text})
        return MagicMock(success=True, message_id="test_msg_id")

    with (
        patch("src.agents.choresir_agent.get_agent", return_value=mock_agent),
        patch("src.core.admin_notifier.send_text_message", side_effect=mock_send_message),
    ):
        # Run agent which should trigger quota exceeded error
        result = await choresir_agent.run_agent(
            user_message="test message",
            deps=deps,
            member_list="Test User (+15551234567)",
        )

        # Verify user receives appropriate error message
        assert "quota" in result.lower() or "service" in result.lower()

        # Verify admin received notification
        assert len(sent_messages) == 1
        admin_msg = sent_messages[0]
        assert admin_msg["to_phone"] == admin["phone"]
        assert "OpenRouter quota exceeded" in admin_msg["text"]
        assert user["name"] in admin_msg["text"]
        assert user["phone"] in admin_msg["text"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_critical_error_notification(mock_db_module, db_client, sample_users: dict) -> None:
    """Test that webhook errors trigger admin notifications for critical errors."""
    # Use alice from sample_users as admin (role="admin" in integration/conftest.py)
    admin = sample_users["alice"]

    # Mock WhatsApp webhook params
    params = {
        "MessageSid": "test_msg_123",
        "From": "whatsapp:+15551234567",
        "Body": "test message",
    }

    # Mock send_text_message to capture notifications
    sent_messages = []

    async def mock_send_message(to_phone: str, text: str):
        sent_messages.append({"to_phone": to_phone, "text": text})
        return MagicMock(success=True, message_id="test_msg_id")

    async def mock_send_group_message(to_group_id: str, text: str):
        sent_messages.append({"to_group_id": to_group_id, "text": text})
        return MagicMock(success=True, message_id="test_msg_id")

    # Mock parse_waha_webhook to return a parsed GROUP message
    mock_parsed = ParsedMessage(
        message_id="test_msg_123",
        from_phone="+15551234567",
        text="test message",
        timestamp="1234567890",
        message_type="text",
        is_group_message=True,
        group_id="group123@g.us",
        actual_sender_phone="+15551234567",
    )

    # Mock house config with configured group
    mock_config = MagicMock()
    mock_config.group_chat_id = "group123@g.us"
    mock_config.activation_key = None

    # Mock build_deps to raise an authentication error (critical)
    async def mock_build_deps(**kwargs):
        raise Exception("Authentication failed: invalid API key")

    with (
        patch(
            "src.interface.webhook.whatsapp_sender.send_text_message",
            side_effect=mock_send_message,
        ),
        patch(
            "src.interface.webhook.whatsapp_sender.send_group_message",
            side_effect=mock_send_group_message,
        ),
        patch(
            "src.interface.webhook.whatsapp_parser.parse_waha_webhook",
            return_value=mock_parsed,
        ),
        patch("src.interface.webhook.get_house_config", return_value=mock_config),
        patch("src.interface.webhook.choresir_agent.build_deps", side_effect=mock_build_deps),
        patch("src.core.admin_notifier.send_text_message", side_effect=mock_send_message),
    ):
        # Process webhook which should trigger critical error
        await webhook.process_webhook_message(params)

        # Verify admin received critical error notification
        admin_notifications = [msg for msg in sent_messages if msg.get("to_phone") == admin["phone"]]
        assert len(admin_notifications) >= 1

        admin_msg = admin_notifications[0]
        assert "Webhook error" in admin_msg["text"]
        assert "authentication_failed" in admin_msg["text"]

        # Verify error message was sent to the user (error messages go via DM, not group)
        user_notifications = [msg for msg in sent_messages if msg.get("to_phone") == "+15551234567"]
        assert len(user_notifications) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_critical_error_no_notification(mock_db_module, db_client, sample_users: dict) -> None:
    """Test that non-critical errors do not trigger admin notifications."""
    # alice is admin from sample_users but should NOT receive notification for non-critical errors

    # Use bob from sample_users as regular user
    user = sample_users["bob"]

    # Create test deps
    deps = Deps(
        db=None,  # SQLite - no db client object needed
        user_id=user["id"],
        user_phone=user["phone"],
        user_name=user["name"],
        user_role=user["role"],
        current_time=datetime.now(),
    )

    # Mock the agent to raise a non-critical error (network error)
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=Exception("Connection timeout"))

    # Mock send_text_message to capture any notifications
    sent_messages = []

    async def mock_send_message(to_phone: str, text: str):
        sent_messages.append({"to_phone": to_phone, "text": text})
        return MagicMock(success=True, message_id="test_msg_id")

    with (
        patch("src.agents.choresir_agent.get_agent", return_value=mock_agent),
        patch("src.core.admin_notifier.send_text_message", side_effect=mock_send_message),
    ):
        # Run agent which should trigger non-critical network error
        result = await choresir_agent.run_agent(
            user_message="test message",
            deps=deps,
            member_list="Test User (+15551234567)",
        )

        # Verify user receives appropriate error message
        assert "network" in result.lower() or "connection" in result.lower()

        # Verify admin did NOT receive notification (network errors are not critical)
        assert len(sent_messages) == 0
