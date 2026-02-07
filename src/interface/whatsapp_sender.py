"""WhatsApp message sender with rate limiting and retry logic using WAHA."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from pydantic import BaseModel, Field

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


def format_phone_for_waha(phone: str) -> str:
    """Format phone number for WAHA (e.g., '1234567890@c.us')."""
    # Remove 'whatsapp:' prefix if present
    clean_phone = phone.replace("whatsapp:", "").replace("+", "").strip()
    # Add suffix if missing
    if not clean_phone.endswith("@c.us"):
        clean_phone = f"{clean_phone}@c.us"
    return clean_phone


def _extract_message_id(data: dict) -> str | None:
    """Extract message ID from WAHA response.

    WAHA returns { "id": ... } where id can be a string or an object.
    If it's an object (e.g., {"fromMe": True, "remote": "...", "_serialized": "..."}),
    extract the _serialized field or convert to string.
    """
    raw_id = data.get("id")
    if isinstance(raw_id, dict):
        return raw_id.get("_serialized") or str(raw_id)
    return raw_id


async def send_text_message(
    *,
    to_phone: str,
    text: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> SendMessageResult:
    """Send a text message via WAHA API with retry logic.

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

    chat_id = format_phone_for_waha(to_phone)
    url = f"{settings.waha_base_url}/api/sendText"
    payload = {
        "session": "default",
        "chatId": chat_id,
        "text": text,
    }
    headers = {"Content-Type": "application/json"}
    if settings.waha_api_key:
        headers["X-Api-Key"] = settings.waha_api_key

    # Retry logic
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=constants.API_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.is_success:
                    message_id = _extract_message_id(response.json())
                    return SendMessageResult(success=True, message_id=message_id)

                # Client error (4xx) - don't retry
                if HTTP_CLIENT_ERROR_START <= response.status_code < HTTP_CLIENT_ERROR_END:
                    return SendMessageResult(success=False, error=f"Client error: {response.text}")

                # Server error (5xx) - allow retry
                raise httpx.HTTPStatusError(
                    f"Server error: {response.status_code}", request=response.request, response=response
                )

        except httpx.HTTPStatusError:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
        except Exception as e:
            # Retry on unexpected errors
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
            else:
                return SendMessageResult(success=False, error=f"Failed after retries: {e!s}")

    return SendMessageResult(success=False, error="Max retries exceeded")


async def send_group_message(
    *,
    to_group_id: str,
    text: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> SendMessageResult:
    """Send a text message to a WhatsApp group via WAHA API with retry logic.

    Args:
        to_group_id: Group JID (e.g., "120363400136168625@g.us")
        text: Message text to send
        max_retries: Maximum number of retry attempts on failure
        retry_delay: Delay in seconds between retries (doubles each retry)

    Returns:
        SendMessageResult indicating success or failure
    """
    # Check rate limit using the group ID
    if not rate_limiter.can_send(to_group_id):
        return SendMessageResult(
            success=False,
            error="Rate limit exceeded. Please try again later.",
        )

    # Record request for rate limiting (before attempting API call)
    rate_limiter.record_request(to_group_id)

    # Group IDs are already in the correct format (e.g., "120363400136168625@g.us")
    # No formatting needed unlike phone numbers
    url = f"{settings.waha_base_url}/api/sendText"
    payload = {
        "session": "default",
        "chatId": to_group_id,
        "text": text,
    }
    headers = {"Content-Type": "application/json"}
    if settings.waha_api_key:
        headers["X-Api-Key"] = settings.waha_api_key

    # Retry logic
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=constants.API_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.is_success:
                    message_id = _extract_message_id(response.json())
                    return SendMessageResult(success=True, message_id=message_id)

                # Client error (4xx) - don't retry
                if HTTP_CLIENT_ERROR_START <= response.status_code < HTTP_CLIENT_ERROR_END:
                    return SendMessageResult(success=False, error=f"Client error: {response.text}")

                # Server error (5xx) - allow retry
                raise httpx.HTTPStatusError(
                    f"Server error: {response.status_code}", request=response.request, response=response
                )

        except httpx.HTTPStatusError:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
        except Exception as e:
            # Retry on unexpected errors
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
            else:
                return SendMessageResult(success=False, error=f"Failed after retries: {e!s}")

    return SendMessageResult(success=False, error="Max retries exceeded")
