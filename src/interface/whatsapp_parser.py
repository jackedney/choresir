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


class ParsedWebhook(BaseModel):
    """Parsed WhatsApp webhook payload."""

    messages: list[ParsedMessage] = Field(default_factory=list, description="List of parsed messages")


def parse_webhook_payload(payload: dict[str, Any]) -> ParsedWebhook:
    """Parse WhatsApp webhook payload into structured data.

    The WhatsApp Cloud API webhook payload structure:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "...",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {...},
                    "messages": [{
                        "from": "1234567890",
                        "id": "wamid.xxx",
                        "timestamp": "1234567890",
                        "type": "text",
                        "text": {"body": "Hello"}
                    }]
                }
            }]
        }]
    }

    Args:
        payload: Raw webhook payload dictionary

    Returns:
        ParsedWebhook containing list of parsed messages
    """
    parsed_messages: list[ParsedMessage] = []

    # Navigate through the nested structure
    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])

            for message in messages:
                # Extract message metadata
                message_id = message.get("id", "")
                from_phone = message.get("from", "")
                timestamp = message.get("timestamp", "")
                message_type = message.get("type", "unknown")

                # Extract text content based on message type
                text = None
                if message_type == "text":
                    text_obj = message.get("text", {})
                    text = text_obj.get("body")
                elif message_type == "button":
                    # Button reply contains text in the payload
                    button_obj = message.get("button", {})
                    text = button_obj.get("text")
                elif message_type == "interactive":
                    # Interactive messages (list/button replies)
                    interactive_obj = message.get("interactive", {})
                    button_reply = interactive_obj.get("button_reply", {})
                    list_reply = interactive_obj.get("list_reply", {})
                    text = button_reply.get("title") or list_reply.get("title")

                # Create parsed message (text can be None for media-only messages)
                parsed_message = ParsedMessage(
                    message_id=message_id,
                    from_phone=from_phone,
                    text=text,
                    timestamp=timestamp,
                    message_type=message_type,
                )
                parsed_messages.append(parsed_message)

    return ParsedWebhook(messages=parsed_messages)


def extract_first_text_message(payload: dict[str, Any]) -> ParsedMessage | None:
    """Extract the first text message from a webhook payload.

    Convenience function for simple use cases where only one message is expected.

    Args:
        payload: Raw webhook payload dictionary

    Returns:
        First ParsedMessage with text content, or None if no text messages found
    """
    parsed = parse_webhook_payload(payload)
    for message in parsed.messages:
        if message.text:
            return message
    return None
