"""WhatsApp message sender with rate limiting and retry logic."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, Field

from src.core.config import constants, settings


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


async def send_text_message(
    *,
    to_phone: str,
    text: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> SendMessageResult:
    """Send a text message via WhatsApp Cloud API with retry logic.

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

    # WhatsApp Cloud API endpoint
    url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }

    # Retry logic
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=constants.API_TIMEOUT_SECONDS) as client:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code == constants.HTTP_OK:
                    data: dict[str, Any] = response.json()
                    message_id = data.get("messages", [{}])[0].get("id")

                    return SendMessageResult(
                        success=True,
                        message_id=message_id,
                    )

                # Handle non-200 responses
                error_data = response.json() if response.text else {}
                error_message = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")

                # Don't retry on client errors (4xx)
                if constants.HTTP_BAD_REQUEST <= response.status_code < constants.HTTP_SERVER_ERROR:
                    return SendMessageResult(
                        success=False,
                        error=f"Client error: {error_message}",
                    )

                # Retry on server errors (5xx)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue

                return SendMessageResult(
                    success=False,
                    error=f"Server error after {max_retries} attempts: {error_message}",
                )

        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
                continue
            return SendMessageResult(
                success=False,
                error=f"Request timeout after {max_retries} attempts",
            )

        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
                continue
            return SendMessageResult(
                success=False,
                error=f"Unexpected error: {e!s}",
            )

    # Should never reach here, but just in case
    return SendMessageResult(
        success=False,
        error="Unknown error occurred",
    )
