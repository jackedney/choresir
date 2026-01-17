"""Tests for WhatsApp webhook parser with Twilio format."""

from src.interface.whatsapp_parser import ParsedMessage, parse_twilio_webhook


class TestParseTwilioWebhook:
    """Test parsing of Twilio webhook form data."""

    def test_parse_valid_text_message(self):
        """Test parsing a valid text message from Twilio."""
        params = {
            "MessageSid": "SM123abc",
            "From": "whatsapp:+1234567890",
            "To": "whatsapp:+14155238886",
            "Body": "Hello, this is a test message",
            "ProfileName": "Test User",
            "WaId": "1234567890",
            "NumMedia": "0",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        assert isinstance(result, ParsedMessage)
        assert result.message_id == "SM123abc"
        assert result.from_phone == "+1234567890"  # Prefix stripped
        assert result.text == "Hello, this is a test message"
        assert result.message_type == "text"
        assert result.timestamp is not None

    def test_parse_message_without_whatsapp_prefix(self):
        """Test parsing when From doesn't have whatsapp: prefix."""
        params = {
            "MessageSid": "SM456def",
            "From": "+1234567890",  # No prefix
            "To": "whatsapp:+14155238886",
            "Body": "Test without prefix",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        assert result.from_phone == "+1234567890"
        assert result.text == "Test without prefix"

    def test_parse_message_without_body(self):
        """Test parsing a message without body (media-only)."""
        params = {
            "MessageSid": "SM789ghi",
            "From": "whatsapp:+1234567890",
            "To": "whatsapp:+14155238886",
            "NumMedia": "1",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        assert result.message_id == "SM789ghi"
        assert result.from_phone == "+1234567890"
        assert result.text is None  # No body
        assert result.message_type == "text"

    def test_parse_empty_params(self):
        """Test parsing with empty parameters."""
        result = parse_twilio_webhook({})

        assert result is None

    def test_parse_missing_message_sid(self):
        """Test parsing when MessageSid is missing."""
        params = {
            "From": "whatsapp:+1234567890",
            "Body": "Test message",
        }

        result = parse_twilio_webhook(params)

        assert result is None

    def test_parse_missing_from(self):
        """Test parsing when From is missing."""
        params = {
            "MessageSid": "SM123abc",
            "Body": "Test message",
        }

        result = parse_twilio_webhook(params)

        assert result is None

    def test_parse_empty_from(self):
        """Test parsing when From is empty string."""
        params = {
            "MessageSid": "SM123abc",
            "From": "",
            "Body": "Test message",
        }

        result = parse_twilio_webhook(params)

        assert result is None

    def test_parse_international_phone_number(self):
        """Test parsing with international phone number."""
        params = {
            "MessageSid": "SM999xyz",
            "From": "whatsapp:+447700900123",  # UK number
            "To": "whatsapp:+14155238886",
            "Body": "Hello from UK",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        assert result.from_phone == "+447700900123"
        assert result.text == "Hello from UK"

    def test_timestamp_is_string(self):
        """Test that timestamp is returned as string (Unix epoch)."""
        params = {
            "MessageSid": "SM111",
            "From": "whatsapp:+1234567890",
            "Body": "Test timestamp",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        assert isinstance(result.timestamp, str)
        # Verify it's a valid Unix timestamp (should be numeric when converted)
        assert int(result.timestamp) > 0

    def test_parsed_message_model_fields(self):
        """Test that ParsedMessage model has all required fields."""
        params = {
            "MessageSid": "SM222",
            "From": "whatsapp:+1234567890",
            "Body": "Test model",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        # Verify all expected fields exist
        assert hasattr(result, "message_id")
        assert hasattr(result, "from_phone")
        assert hasattr(result, "text")
        assert hasattr(result, "timestamp")
        assert hasattr(result, "message_type")
        assert hasattr(result, "button_payload")

    def test_special_characters_in_body(self):
        """Test parsing message with special characters."""
        params = {
            "MessageSid": "SM333",
            "From": "whatsapp:+1234567890",
            "Body": "Hello! 👋 Test with émoji & spëcial chars: @#$%",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        assert result.text == "Hello! 👋 Test with émoji & spëcial chars: @#$%"

    def test_multiline_body(self):
        """Test parsing message with newlines."""
        params = {
            "MessageSid": "SM444",
            "From": "whatsapp:+1234567890",
            "Body": "Line 1\nLine 2\nLine 3",
        }

        result = parse_twilio_webhook(params)

        assert result is not None
        assert result.text == "Line 1\nLine 2\nLine 3"
        assert "\n" in result.text

    def test_parse_button_reply_approve(self):
        """Test parsing an Approve button click."""
        params = {
            "MessageSid": "SM123",
            "From": "whatsapp:+1234567890",
            "Body": "Approve",
            "ButtonPayload": "VERIFY:APPROVE:log123",
        }
        result = parse_twilio_webhook(params)
        assert result is not None
        assert result.message_type == "button_reply"
        assert result.button_payload == "VERIFY:APPROVE:log123"
        assert result.text == "Approve"

    def test_parse_button_reply_reject(self):
        """Test parsing a Reject button click."""
        params = {
            "MessageSid": "SM456",
            "From": "whatsapp:+1234567890",
            "Body": "Reject",
            "ButtonPayload": "VERIFY:REJECT:log456",
        }
        result = parse_twilio_webhook(params)
        assert result is not None
        assert result.message_type == "button_reply"
        assert result.button_payload == "VERIFY:REJECT:log456"

    def test_parse_text_message_no_payload(self):
        """Test regular text messages have no button_payload."""
        params = {
            "MessageSid": "SM789",
            "From": "whatsapp:+1234567890",
            "Body": "Regular text message",
        }
        result = parse_twilio_webhook(params)
        assert result is not None
        assert result.message_type == "text"
        assert result.button_payload is None
