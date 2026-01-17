"""WhatsApp message sender with rate limiting and retry logic."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from src.core.config import constants, settings


# HTTP status code constants for error handling
HTTP_CLIENT_ERROR_START = 400
HTTP_CLIENT_ERROR_END = 500


class SendMessageResult(BaseModel):
    """Result of sending a WhatsApp message."""

    success: bool = Field(..., description="Whether the message was sent successfully")
    message_id: str | None = Field(None, description="WhatsApp message ID if successful")
    error: str | None = Field(None, description="Error message if failed")


class RateLimiter:
    """In-memory rate limiter for WhatsApp API calls.

    Tracks requests per phone number per minute to prevent exceeding rate limits.
    """

    def __init__(self) -> None:
        """Initialize rate limiter."""
        self._requests: dict[str, list[datetime]] = defaultdict(list)

    def can_send(self, phone: str) -> bool:
        """Check if a message can be sent to the given phone number.

        Args:
            phone: Phone number to check

        Returns:
            True if sending is allowed, False if rate limited
        """
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)

        # Clean up old requests
        self._requests[phone] = [ts for ts in self._requests[phone] if ts > cutoff]

        # Check if under limit
        return len(self._requests[phone]) < constants.MAX_REQUESTS_PER_MINUTE

    def record_request(self, phone: str) -> None:
        """Record a request for rate limiting.

        Args:
            phone: Phone number to record
        """
        self._requests[phone].append(datetime.now())


# Global rate limiter instance (in-memory for MVP)
rate_limiter = RateLimiter()


class _TwilioClientSingleton:
    """Singleton wrapper for Twilio client to avoid global statement."""

    _instance: Client | None = None

    @classmethod
    def get_client(cls) -> Client:
        """Get or create the Twilio client instance.

        Returns:
            Initialized Twilio client
        """
        if cls._instance is None:
            account_sid = settings.require_credential("twilio_account_sid", "Twilio Account SID")
            auth_token = settings.require_credential("twilio_auth_token", "Twilio Auth Token")
            cls._instance = Client(account_sid, auth_token)
        return cls._instance


def get_twilio_client() -> Client:
    """Get or create the Twilio client instance.

    Returns:
        Initialized Twilio client
    """
    return _TwilioClientSingleton.get_client()


async def send_text_message(
    *,
    to_phone: str,
    text: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> SendMessageResult:
    """Send a text message via Twilio WhatsApp API with retry logic.

    Args:
        to_phone: Recipient phone number in E.164 format (e.g., "1234567890")
        text: Message text to send
        max_retries: Maximum number of retry attempts on failure
        retry_delay: Delay in seconds between retries (doubles each retry)

    Returns:
        SendMessageResult indicating success or failure
    """
    # Check rate limit
    if not rate_limiter.can_send(to_phone):
        return SendMessageResult(
            success=False,
            error="Rate limit exceeded. Please try again later.",
        )

    # Record request for rate limiting (before attempting API call)
    rate_limiter.record_request(to_phone)

    # Format phone number for Twilio WhatsApp
    to_whatsapp = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone

    # Retry logic
    for attempt in range(max_retries):
        try:
            client = get_twilio_client()
            message = client.messages.create(
                from_=settings.twilio_whatsapp_number,
                to=to_whatsapp,
                body=text,
            )
            return SendMessageResult(success=True, message_id=message.sid)

        except TwilioRestException as e:
            # Don't retry on client errors (4xx)
            if e.status >= HTTP_CLIENT_ERROR_START and e.status < HTTP_CLIENT_ERROR_END:
                return SendMessageResult(success=False, error=f"Client error: {e.msg}")

            # Retry on server errors (5xx)
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))

        except Exception:
            # Retry on unexpected errors
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))

    return SendMessageResult(success=False, error="Max retries exceeded")
