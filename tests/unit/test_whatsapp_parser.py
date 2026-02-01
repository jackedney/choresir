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
            "type": "chat"
        }
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
        "type": "chat"
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.message_id == "true_1234567890@c.us_ABC"
    assert result.from_phone == "+1234567890"

def test_parse_ignore_status_broadcast():
    """Test ignoring status@broadcast messages."""
    data = {
        "payload": {
            "id": "...",
            "from": "status@broadcast",
            "body": "status",
            "timestamp": 123
        }
    }
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
            "selectedButtonId": "VERIFY:APPROVE:1"
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
            "_data": {
                "selectedButtonId": "VERIFY:APPROVE:1"
            }
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
            "_data": {
                "selectedRowId": "OPTION_1"
            }
        }
    }
    result = parse_waha_webhook(data)
    assert result is not None
    assert result.message_type == "button_reply" # Mapped to button reply for app logic compatibility
    assert result.button_payload == "OPTION_1"

def test_parse_invalid_data():
    """Test parsing invalid data returns None."""
    assert parse_waha_webhook({}) is None
    assert parse_waha_webhook({"payload": {}}) is None
    assert parse_waha_webhook({"payload": {"id": "1"}}) is None # Missing 'from'
