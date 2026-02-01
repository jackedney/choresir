"""WhatsApp webhook payload parser."""

from typing import Any

from pydantic import BaseModel, Field


class ParsedMessage(BaseModel):
    """Parsed WhatsApp message data."""

    message_id: str = Field(..., description="Unique message ID from WhatsApp")
    from_phone: str = Field(..., description="Sender phone number in E.164 format")
    text: str | None = Field(None, description="Text content of the message (None for media-only messages)")
    timestamp: str = Field(..., description="Message timestamp (Unix epoch as string)")
    message_type: str = Field(..., description="Type of message (text, image, audio, etc.)")
    button_payload: str | None = Field(None, description="Button payload for interactive message responses")


def parse_waha_webhook(data: dict[str, Any]) -> ParsedMessage | None:
    """Parse WAHA WhatsApp webhook JSON data.

    WAHA sends webhooks with structure:
    {
        "event": "message",
        "payload": {
            "id": "true_1234567890@c.us_ABC123",
            "from": "1234567890@c.us",
            "body": "Hello",
            "timestamp": 1678900000,
            "type": "chat",
            "_data": { ... }
        }
    }

    Args:
        data: Parsed JSON webhook data

    Returns:
        ParsedMessage if valid webhook data, None otherwise
    """
    # Extract payload
    # Handle both wrapped {event: ..., payload: ...} and direct payload
    payload = data.get("payload", data)

    # Basic validation
    msg_id = payload.get("id")
    from_raw = payload.get("from")

    if not msg_id or not from_raw:
        return None

    # Check for required timestamp field (only if basic fields are present)
    timestamp = payload.get("timestamp")
    if timestamp is None or timestamp == "":
        raise ValueError("Missing required timestamp in webhook payload")

    # Ignore status updates or other events if they sneak in
    # (WAHA usually sends "message" event for incoming messages)
    # If "from" is "status@broadcast", ignore it
    if from_raw == "status@broadcast":
        return None

    # Clean phone number
    # Remove @c.us suffix
    clean_number = from_raw.replace("@c.us", "")

    # Ensure E.164 format with + prefix for consistency with existing database records
    # WAHA usually sends '1234567890', we want '+1234567890'
    from_phone = f"+{clean_number}" if not clean_number.startswith("+") else clean_number

    # Extract content
    body = payload.get("body")
    timestamp = str(payload.get("timestamp", ""))
    msg_type = payload.get("type", "text")

    # Handle Button Responses
    # WAHA/WebJS often puts button selection ID in specialized fields
    # or sometimes just the body contains the text.
    # For robust button handling (payloads), we look for specific fields.
    button_payload = None

    # Check for button response details in _data or root payload
    # Note: WAHA structure varies by engine (WEBJS vs GOWS).
    # We attempt to find a 'selectedButtonId' or similar.
    # If using WAHA Plus or specific engines, it might be in `selectedButtonId`.
    if msg_type == "buttons_response":
        button_payload = payload.get("selectedButtonId")
        if not button_payload and "_data" in payload:
            button_payload = payload["_data"].get("selectedButtonId")

    # Also check list response
    if msg_type == "list_response":
        button_payload = payload.get("selectedRowId")
        if not button_payload and "_data" in payload:
            button_payload = payload["_data"].get("selectedRowId")

    # Map message type to application types
    # Application expects: text, button_reply, etc.
    app_message_type = "text"
    if button_payload:
        app_message_type = "button_reply"

    return ParsedMessage(
        message_id=msg_id,
        from_phone=from_phone,
        text=body,
        timestamp=timestamp,
        message_type=app_message_type,
        button_payload=button_payload,
    )
