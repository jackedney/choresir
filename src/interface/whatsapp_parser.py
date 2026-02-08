"""WhatsApp webhook payload parser."""

import re
from typing import Any

from pydantic import BaseModel, Field


def _clean_whatsapp_id(whatsapp_id: str) -> str | None:
    """Return cleaned phone number from a WhatsApp ID or None for non-phone IDs."""
    if not whatsapp_id:
        return None

    # Skip @lid format - these are linked IDs, not phone numbers
    if "@lid" in whatsapp_id:
        return None

    # Remove known WhatsApp suffixes
    clean = whatsapp_id
    for suffix in ("@c.us", "@s.whatsapp.net", "@g.us"):
        clean = clean.replace(suffix, "")

    # Validate it looks like a phone number (digits only, reasonable length)
    # E.164 numbers are 1-15 digits
    if not re.match(r"^\d{1,15}$", clean):
        return None

    return clean


class ParsedMessage(BaseModel):
    """Parsed WhatsApp message data."""

    message_id: str = Field(..., description="Unique message ID from WhatsApp")
    from_phone: str = Field(..., description="Sender phone number in E.164 format")
    text: str | None = Field(None, description="Text content of the message (None for media-only messages)")
    timestamp: str = Field(..., description="Message timestamp (Unix epoch as string)")
    message_type: str = Field(..., description="Type of message (text, image, audio, etc.)")
    button_payload: str | None = Field(None, description="Button payload for interactive message responses")
    is_group_message: bool = Field(False, description="True if message is from a group chat")
    group_id: str | None = Field(
        None, description="Group JID if this is a group message (e.g., 120363400136168625@g.us)"
    )
    actual_sender_phone: str | None = Field(None, description="Real sender's phone in group messages")
    participant_lid: str | None = Field(None, description="Raw participant @lid if phone couldn't be resolved")
    reply_to_message_id: str | None = Field(None, description="Message ID being replied to, if this is a reply/quote")


class _GroupMessageInfo:
    """Container for group message parsing results."""

    def __init__(
        self,
        group_id: str | None = None,
        actual_sender_phone: str | None = None,
        participant_lid: str | None = None,
    ) -> None:
        self.group_id = group_id
        self.actual_sender_phone = actual_sender_phone
        self.participant_lid = participant_lid


def _parse_group_message_info(from_raw: str, payload: dict[str, Any]) -> _GroupMessageInfo:
    """Extract group message information from payload.

    Args:
        from_raw: The raw "from" field value
        payload: The webhook payload

    Returns:
        GroupMessageInfo with group_id, actual_sender_phone, and participant_lid
    """
    info = _GroupMessageInfo(group_id=from_raw)

    participant = payload.get("participant", "")
    if participant:
        clean_participant = _clean_whatsapp_id(participant)
        if clean_participant:
            info.actual_sender_phone = f"+{clean_participant}"
        elif "@lid" in participant:
            info.participant_lid = participant

    return info


def _resolve_from_phone(
    is_group_message: bool,
    clean_number: str | None,
    actual_sender_phone: str | None,
) -> str | None:
    """Resolve the from_phone value based on message context.

    Args:
        is_group_message: Whether this is a group message
        clean_number: Cleaned phone number from the "from" field
        actual_sender_phone: Actual sender phone for group messages

    Returns:
        The resolved from_phone, or None if invalid individual message
    """
    if is_group_message:
        return f"+{clean_number}" if clean_number else actual_sender_phone or ""

    if not clean_number:
        return None

    return f"+{clean_number}"


def _extract_button_payload(msg_type: str, payload: dict[str, Any]) -> str | None:
    """Extract button payload from interactive message responses.

    Args:
        msg_type: The message type from the payload
        payload: The webhook payload

    Returns:
        Button payload ID if present, None otherwise
    """
    if msg_type == "buttons_response":
        button_payload = payload.get("selectedButtonId")
        if not button_payload and "_data" in payload:
            button_payload = payload["_data"].get("selectedButtonId")
        return button_payload

    if msg_type == "list_response":
        button_payload = payload.get("selectedRowId")
        if not button_payload and "_data" in payload:
            button_payload = payload["_data"].get("selectedRowId")
        return button_payload

    return None


def _extract_reply_to_message_id(payload: dict[str, Any]) -> str | None:
    """Extract the reply-to message ID from payload.

    Args:
        payload: The webhook payload

    Returns:
        The message ID being replied to, or None
    """
    reply_to_raw = payload.get("replyTo")
    if not reply_to_raw:
        return None

    if isinstance(reply_to_raw, str):
        return reply_to_raw

    if isinstance(reply_to_raw, dict):
        return reply_to_raw.get("id") or reply_to_raw.get("messageId")

    return None


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
    payload = data.get("payload", data)

    msg_id = payload.get("id")
    from_raw = payload.get("from")

    if not msg_id or not from_raw:
        return None

    if from_raw == "status@broadcast":
        return None

    is_group_message = from_raw.endswith("@g.us")
    group_info = _GroupMessageInfo()

    if is_group_message:
        group_info = _parse_group_message_info(from_raw, payload)

    clean_number = _clean_whatsapp_id(from_raw)
    from_phone = _resolve_from_phone(is_group_message, clean_number, group_info.actual_sender_phone)

    if from_phone is None:
        return None

    msg_type = payload.get("type", "text")
    button_payload = _extract_button_payload(msg_type, payload)
    app_message_type = "button_reply" if button_payload else "text"

    return ParsedMessage(
        message_id=msg_id,
        from_phone=from_phone,
        text=payload.get("body"),
        timestamp=str(payload.get("timestamp", "")),
        message_type=app_message_type,
        button_payload=button_payload,
        is_group_message=is_group_message,
        group_id=group_info.group_id,
        actual_sender_phone=group_info.actual_sender_phone,
        participant_lid=group_info.participant_lid,
        reply_to_message_id=_extract_reply_to_message_id(payload),
    )
