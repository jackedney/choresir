"""WhatsApp message sender with rate limiting and retry logic using WAHA."""

import asyncio
import functools
import logging
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from pydantic import BaseModel, Field

from src.core.config import constants, settings


logger = logging.getLogger(__name__)


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


@functools.cache
def format_phone_for_waha(phone: str) -> str:
    """Format phone number for WAHA (e.g., '1234567890@c.us')."""
    # Remove 'whatsapp:' prefix if present
    clean_phone = phone.replace("whatsapp:", "").replace("+", "").strip()
    # Add suffix if missing
    if not clean_phone.endswith("@c.us"):
        clean_phone = f"{clean_phone}@c.us"
    return clean_phone


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
    logger.debug("Sending text message", extra={"operation": "send_message_start"})

    # Check rate limit
    if not rate_limiter.can_send(to_phone):
        logger.warning("Rate limit exceeded", extra={"operation": "send_rate_limited"})
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
                    data = response.json()
                    # WAHA returns { "id": "...", ... }
                    message_id = data.get("id")
                    logger.info(
                        "Message sent successfully",
                        extra={"operation": "send_message_success", "message_id": message_id},
                    )
                    return SendMessageResult(success=True, message_id=message_id)

                # Client error (4xx) - don't retry
                if HTTP_CLIENT_ERROR_START <= response.status_code < HTTP_CLIENT_ERROR_END:
                    return SendMessageResult(success=False, error=f"Client error: {response.text}")

                # Server error (5xx) - allow retry
                raise httpx.HTTPStatusError(
                    f"Server error: {response.status_code}", request=response.request, response=response
                )

        except httpx.HTTPStatusError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
            else:
                logger.error(
                    "Server error after retries",
                    extra={"operation": "send_message_failed", "status_code": e.response.status_code},
                )
                return SendMessageResult(success=False, error=f"Failed after retries: {e}")
        except (httpx.ConnectError, httpx.NetworkError, httpx.HTTPError) as e:
            # Retry on httpx errors
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
            else:
                logger.error(
                    "Failed to send message", extra={"operation": "send_message_failed", "error_type": type(e).__name__}
                )
                return SendMessageResult(success=False, error=f"Failed after retries: {e}")

    logger.error("WAHA send failed after retries", extra={"max_retries": max_retries})
    return SendMessageResult(success=False, error="Max retries exceeded")
