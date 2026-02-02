"""Webhook security utilities for replay attack protection."""

import hashlib
import hmac
import logging
from datetime import datetime
from typing import NamedTuple

from src.core.config import Constants, constants
from src.core.redis_client import redis_client


logger = logging.getLogger(__name__)


class WebhookSecurityResult(NamedTuple):
    """Result of webhook security validation."""

    is_valid: bool
    error_message: str | None
    http_status_code: int | None


async def validate_webhook_timestamp(timestamp_str: str) -> WebhookSecurityResult:
    """Validate webhook timestamp is within acceptable age.

    Args:
        timestamp_str: Unix timestamp string from webhook

    Returns:
        WebhookSecurityResult indicating if timestamp is valid
    """
    try:
        webhook_timestamp = int(timestamp_str)
    except (ValueError, TypeError):
        logger.warning(f"Invalid timestamp format: {timestamp_str}")
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Invalid timestamp format",
            http_status_code=400,
        )

    current_timestamp = int(datetime.now().timestamp())
    age_seconds = current_timestamp - webhook_timestamp

    if age_seconds < 0:
        logger.warning(f"Webhook timestamp in future: {timestamp_str}")
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Timestamp is in the future",
            http_status_code=400,
        )

    if age_seconds > constants.WEBHOOK_MAX_AGE_SECONDS:
        logger.warning(
            "Webhook expired (age: %ds, max: %ds)",
            age_seconds,
            constants.WEBHOOK_MAX_AGE_SECONDS,
            extra={"webhook_age_seconds": age_seconds, "max_age_seconds": constants.WEBHOOK_MAX_AGE_SECONDS},
        )
        return WebhookSecurityResult(
            is_valid=False,
            error_message=f"Webhook expired (age: {age_seconds}s)",
            http_status_code=400,
        )

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)


async def validate_webhook_nonce(message_id: str) -> WebhookSecurityResult:
    """Validate webhook hasn't been processed before (nonce check).

    Args:
        message_id: Unique message ID from webhook

    Returns:
        WebhookSecurityResult indicating if nonce is valid (not a duplicate)
    """
    if not redis_client.is_available:
        logger.warning("Redis not available, skipping nonce validation")
        return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

    nonce_key = f"webhook:nonce:{message_id}"

    was_set = await redis_client.set_if_not_exists(
        key=nonce_key,
        value="1",
        ttl_seconds=constants.WEBHOOK_NONCE_TTL_SECONDS,
    )

    if not was_set:
        logger.warning(
            "Duplicate webhook detected: %s",
            message_id,
            extra={"message_id": message_id},
        )
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Duplicate webhook",
            http_status_code=400,
        )

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)


def validate_webhook_hmac(*, raw_body: bytes, signature: str | None, secret: str) -> WebhookSecurityResult:
    """Validate webhook HMAC signature.

    Computes SHA256 HMAC of raw request body using secret key and compares
    with the provided signature header using constant-time comparison.

    Args:
        raw_body: Raw bytes of the request body
        signature: X-Hub-Signature-256 header value (hex-encoded HMAC)
        secret: Secret key used to compute HMAC

    Returns:
        WebhookSecurityResult indicating if signature is valid
    """
    if signature is None:
        logger.warning("Missing X-Hub-Signature-256 header")
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Missing webhook signature",
            http_status_code=401,
        )

    expected_signature = hmac.new(
        secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        logger.warning("Invalid webhook signature")
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Invalid webhook signature",
            http_status_code=401,
        )

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)


async def validate_webhook_rate_limit(phone_number: str) -> WebhookSecurityResult:
    """Validate webhook rate limit per phone number.

    Args:
        phone_number: Phone number making the request

    Returns:
        WebhookSecurityResult indicating if rate limit is respected
    """
    if not redis_client.is_available:
        logger.warning("Redis not available, skipping rate limit validation")
        return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

    rate_limit_key = f"webhook:ratelimit:{phone_number}"

    count = await redis_client.increment(rate_limit_key)

    if count is None:
        logger.warning("Failed to increment rate limit counter")
        return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

    if count == 1:
        await redis_client.expire(rate_limit_key, Constants.RATE_LIMIT_WINDOW_SECONDS)

    if count > constants.WEBHOOK_RATE_LIMIT_PER_PHONE:
        logger.warning(
            "Rate limit exceeded for %s: %d requests/min",
            phone_number,
            count,
            extra={
                "phone_number": phone_number,
                "request_count": count,
                "limit": constants.WEBHOOK_RATE_LIMIT_PER_PHONE,
            },
        )
        return WebhookSecurityResult(
            is_valid=False,
            error_message=f"Rate limit exceeded: {count} requests per minute",
            http_status_code=429,
        )

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)


async def verify_webhook_security(message_id: str, timestamp_str: str, phone_number: str) -> WebhookSecurityResult:
    """Perform all webhook security validations.

    Args:
        message_id: Unique message ID
        timestamp_str: Unix timestamp string
        phone_number: Phone number making the request

    Returns:
        WebhookSecurityResult with validation result
    """
    timestamp_result = await validate_webhook_timestamp(timestamp_str)
    if not timestamp_result.is_valid:
        return timestamp_result

    nonce_result = await validate_webhook_nonce(message_id)
    if not nonce_result.is_valid:
        return nonce_result

    rate_limit_result = await validate_webhook_rate_limit(phone_number)
    if not rate_limit_result.is_valid:
        return rate_limit_result

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)
