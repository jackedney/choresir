"""Tests for WAHA webhook parser."""

from src.interface.whatsapp_parser import parse_waha_webhook


def test_parse_simple_text_message():
    """Test parsing a standard text message."""
    data = {
        "event": "message",
        "payload": {
            "id": "true_1234567890@c.us_ABC",
            "from": "1234567890@c.us",
            "body": "Hello",
            "timestamp": 1678900000,
            "type": "chat",
        },
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.message_id == "true_1234567890@c.us_ABC"
    assert result.from_phone == "+1234567890"
    assert result.text == "Hello"
    assert result.message_type == "text"
    assert result.button_payload is None


def test_parse_direct_payload():
    """Test parsing a payload that is not wrapped in event."""
    data = {
        "id": "true_1234567890@c.us_ABC",
        "from": "1234567890@c.us",
        "body": "Hello",
        "timestamp": 1678900000,
        "type": "chat",
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.message_id == "true_1234567890@c.us_ABC"
    assert result.from_phone == "+1234567890"


def test_parse_ignore_status_broadcast():
    """Test ignoring status@broadcast messages."""
    data = {"payload": {"id": "...", "from": "status@broadcast", "body": "status", "timestamp": 123}}
    result = parse_waha_webhook(data)
    assert result is None


def test_parse_button_response_selected_id_root():
    """Test parsing button response where selectedButtonId is in payload root (WAHA Plus/Some engines)."""
    data = {
        "payload": {
            "id": "msg_id",
            "from": "123@c.us",
            "body": "Button Text",
            "timestamp": 123,
            "type": "buttons_response",
            "selectedButtonId": "VERIFY:APPROVE:1",
        }
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.message_type == "button_reply"
    assert result.button_payload == "VERIFY:APPROVE:1"


def test_parse_button_response_selected_id_data():
    """Test parsing button response where selectedButtonId is in _data (Standard WebJS)."""
    data = {
        "payload": {
            "id": "msg_id",
            "from": "123@c.us",
            "body": "Button Text",
            "timestamp": 123,
            "type": "buttons_response",
            "_data": {"selectedButtonId": "VERIFY:APPROVE:1"},
        }
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.message_type == "button_reply"
    assert result.button_payload == "VERIFY:APPROVE:1"


def test_parse_list_response():
    """Test parsing list response."""
    data = {
        "payload": {
            "id": "msg_id",
            "from": "123@c.us",
            "body": "List Text",
            "timestamp": 123,
            "type": "list_response",
            "_data": {"selectedRowId": "OPTION_1"},
        }
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.message_type == "button_reply"  # Mapped to button reply for app logic compatibility
    assert result.button_payload == "OPTION_1"


def test_parse_invalid_data():
    """Test parsing invalid data returns None."""
    assert parse_waha_webhook({}) is None
    assert parse_waha_webhook({"payload": {}}) is None
    assert parse_waha_webhook({"payload": {"id": "1"}}) is None  # Missing 'from'


def test_parse_lid_format_individual_message():
    """Test that @lid format individual messages are rejected (not valid phone numbers)."""
    data = {
        "payload": {
            "id": "msg_id",
            "from": "118777370906868@lid",
            "body": "Hello",
            "timestamp": 123,
            "type": "chat",
        }
    }
    result = parse_waha_webhook(data)
    # @lid format should be rejected - not a valid phone number
    assert result is None


def test_parse_group_message_with_lid_participant():
    """Test group message where participant has @lid format."""
    data = {
        "payload": {
            "id": "msg_id",
            "from": "120363400136168625@g.us",
            "participant": "118777370906868@lid",
            "body": "Hello group",
            "timestamp": 123,
            "type": "chat",
        }
    }
    result = parse_waha_webhook(data)
    # Message should be parsed but actual_sender_phone should be None
    # participant_lid should be set for later resolution via WAHA API
    assert result is not None
    assert result.is_group_message is True
    assert result.group_id == "120363400136168625@g.us"
    assert result.actual_sender_phone is None
    assert result.participant_lid == "118777370906868@lid"
    # from_phone falls back to empty string when participant is invalid
    assert result.from_phone == ""


def test_parse_group_message_with_valid_participant():
    """Test group message with valid participant phone."""
    data = {
        "payload": {
            "id": "msg_id",
            "from": "120363400136168625@g.us",
            "participant": "447871681224@c.us",
            "body": "Hello group",
            "timestamp": 123,
            "type": "chat",
        }
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.is_group_message is True
    assert result.group_id == "120363400136168625@g.us"
    assert result.actual_sender_phone == "+447871681224"
    assert result.from_phone == "+447871681224"


def test_parse_reply_to_message():
    """Test parsing a message that is a reply to another message."""
    data = {
        "payload": {
            "id": "true_1234567890@c.us_ABC",
            "from": "1234567890@c.us",
            "body": "Yes",
            "timestamp": 1678900000,
            "type": "chat",
            "replyTo": "false_1234567890@c.us_XYZ123",
        }
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.text == "Yes"
    assert result.reply_to_message_id == "false_1234567890@c.us_XYZ123"


def test_parse_message_without_reply():
    """Test that messages without replyTo have reply_to_message_id as None."""
    data = {
        "payload": {
            "id": "true_1234567890@c.us_ABC",
            "from": "1234567890@c.us",
            "body": "Hello",
            "timestamp": 1678900000,
            "type": "chat",
        }
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.reply_to_message_id is None
