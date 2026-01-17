"""WhatsApp webhook payload parser."""

from datetime import datetime

from pydantic import BaseModel, Field


class ParsedMessage(BaseModel):
    """Parsed WhatsApp message data."""

    message_id: str = Field(..., description="Unique message ID from WhatsApp")
    from_phone: str = Field(..., description="Sender phone number in E.164 format")
    text: str | None = Field(None, description="Text content of the message (None for media-only messages)")
    timestamp: str = Field(..., description="Message timestamp (Unix epoch as string)")
    message_type: str = Field(..., description="Type of message (text, image, audio, etc.)")
    button_payload: str | None = Field(None, description="Button payload for interactive message responses")


def parse_twilio_webhook(params: dict[str, str]) -> ParsedMessage | None:
    """Parse Twilio WhatsApp webhook form data.

    Twilio sends webhooks as form-encoded data with flat parameters:
    {
        "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "From": "whatsapp:+1234567890",
        "To": "whatsapp:+14155238886",
        "Body": "Hello",
        "ProfileName": "John Doe",
        "WaId": "1234567890",
        "NumMedia": "0"
    }

    Args:
        params: Form-encoded webhook parameters from Twilio

    Returns:
        ParsedMessage if valid webhook data, None otherwise
    """
    message_sid = params.get("MessageSid")
    from_phone = params.get("From", "")
    body = params.get("Body")
    button_payload = params.get("ButtonPayload")

    if not message_sid or not from_phone:
        return None

    # Strip whatsapp: prefix
    if from_phone.startswith("whatsapp:"):
        from_phone = from_phone[9:]

    # Determine message type from webhook parameters
    # Twilio sends different fields based on the type of user interaction.
    # Priority order (first match wins):
    # 1. ButtonPayload -> button_reply (interactive button response)
    # 2. ListReply -> list_reply (future: list selection)
    # 3. QuickReply -> quick_reply (future: quick reply button)
    # 4. Latitude/Longitude -> location (future: location share)
    # 5. Default -> text (regular text message)
    message_type = "button_reply" if button_payload else "text"

    return ParsedMessage(
        message_id=message_sid,
        from_phone=from_phone,
        text=body,
        timestamp=str(int(datetime.now().timestamp())),
        message_type=message_type,
        button_payload=button_payload,
    )
