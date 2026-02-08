"""WhatsApp message sender with rate limiting and retry logic using WAHA."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from pydantic import BaseModel, Field

from src.core import db_client
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


async def _store_bot_message(*, message_id: str, text: str, chat_id: str) -> None:
    """Store a sent bot message for reply context lookup.

    Args:
        message_id: WhatsApp message ID
        text: Message text content
        chat_id: Chat ID the message was sent to
    """
    try:
        await db_client.create_record(
            collection="bot_messages",
            data={
                "message_id": message_id,
                "text": text,
                "chat_id": chat_id,
                "sent_at": datetime.now().isoformat(),
            },
        )
    except Exception as e:
        # Don't fail the send if storage fails - just log it
        logger.warning("Failed to store bot message %s: %s", message_id, e)


async def get_bot_message_text(message_id: str) -> str | None:
    """Retrieve the text of a previously sent bot message.

    Args:
        message_id: WhatsApp message ID to look up

    Returns:
        Message text if found, None otherwise
    """
    try:
        record = await db_client.get_first_record(
            collection="bot_messages",
            filter_query=f'message_id = "{db_client.sanitize_param(message_id)}"',
        )
        if record:
            return record.get("text")
    except Exception as e:
        logger.warning("Failed to retrieve bot message %s: %s", message_id, e)
    return None


async def _send_waha_message(
    *,
    chat_id: str,
    text: str,
    max_retries: int,
    retry_delay: float,
) -> SendMessageResult:
    """Core message sending logic with retry."""
    url = f"{settings.waha_base_url}/api/sendText"
    payload = {"session": "default", "chatId": chat_id, "text": text}
    headers = {"Content-Type": "application/json"}
    if settings.waha_api_key:
        headers["X-Api-Key"] = settings.waha_api_key

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=constants.API_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.is_success:
                    message_id = _extract_message_id(response.json())
                    if message_id:
                        await _store_bot_message(message_id=message_id, text=text, chat_id=chat_id)
                    return SendMessageResult(success=True, message_id=message_id)

                if HTTP_CLIENT_ERROR_START <= response.status_code < HTTP_CLIENT_ERROR_END:
                    return SendMessageResult(success=False, error=f"Client error: {response.text}")

                raise httpx.HTTPStatusError(
                    f"Server error: {response.status_code}", request=response.request, response=response
                )
        except httpx.HTTPStatusError:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2**attempt))
            else:
                return SendMessageResult(success=False, error=f"Failed after retries: {e!s}")

    return SendMessageResult(success=False, error="Max retries exceeded")


async def send_text_message(
    *,
    to_phone: str,
    text: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> SendMessageResult:
    """Send a text message via WAHA API with retry logic."""
    if not rate_limiter.can_send(to_phone):
        return SendMessageResult(success=False, error="Rate limit exceeded. Please try again later.")

    rate_limiter.record_request(to_phone)
    chat_id = format_phone_for_waha(to_phone)
    return await _send_waha_message(chat_id=chat_id, text=text, max_retries=max_retries, retry_delay=retry_delay)


async def send_group_message(
    *,
    to_group_id: str,
    text: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> SendMessageResult:
    """Send a text message to a WhatsApp group via WAHA API with retry logic."""
    if not rate_limiter.can_send(to_group_id):
        return SendMessageResult(success=False, error="Rate limit exceeded. Please try again later.")

    rate_limiter.record_request(to_group_id)
    return await _send_waha_message(chat_id=to_group_id, text=text, max_retries=max_retries, retry_delay=retry_delay)
