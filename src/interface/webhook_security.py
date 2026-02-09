"""Webhook security utilities for replay attack protection."""

import logging
import secrets
from datetime import datetime
from typing import NamedTuple

from src.core.cache_client import cache_client
from src.core.config import Constants, constants


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
        logger.warning("Invalid timestamp format: %s", timestamp_str)
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Invalid timestamp format",
            http_status_code=400,
        )

    current_timestamp = int(datetime.now().timestamp())
    age_seconds = current_timestamp - webhook_timestamp

    if age_seconds < 0:
        logger.warning("Webhook timestamp in future: %s", timestamp_str)
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
    if not cache_client.is_available:
        logger.warning("Cache not available, skipping nonce validation")
        return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

    nonce_key = f"webhook:nonce:{message_id}"

    was_set = await cache_client.set_if_not_exists(
        key=nonce_key,
        value="1",
        ttl_seconds=constants.WEBHOOK_NONCE_TTL_SECONDS,
    )

    if not was_set:
        logger.debug(
            "Duplicate webhook detected: %s",
            message_id,
            extra={"message_id": message_id},
        )
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Duplicate webhook",
            http_status_code=200,
        )

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)


async def validate_webhook_rate_limit(phone_number: str) -> WebhookSecurityResult:
    """Validate webhook rate limit per phone number.

    Args:
        phone_number: Phone number making the request

    Returns:
        WebhookSecurityResult indicating if rate limit is respected
    """
    if not cache_client.is_available:
        logger.warning("Cache not available, skipping rate limit validation")
        return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

    rate_limit_key = f"webhook:ratelimit:{phone_number}"

    count = await cache_client.increment(rate_limit_key)

    if count is None:
        logger.warning("Failed to increment rate limit counter")
        return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

    if count == 1:
        await cache_client.expire(rate_limit_key, Constants.RATE_LIMIT_WINDOW_SECONDS)

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


async def validate_webhook_secret(received_secret: str | None, expected_secret: str | None) -> WebhookSecurityResult:
    """Validate webhook secret (authentication).

    Args:
        received_secret: Secret received in request header
        expected_secret: Secret configured in settings

    Returns:
        WebhookSecurityResult indicating if secret is valid
    """
    if not expected_secret:
        # Secret not configured, skip validation (fail open for backward compatibility)
        return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

    if not received_secret:
        logger.warning("Missing webhook secret")
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Missing webhook secret",
            http_status_code=401,
        )

    if not secrets.compare_digest(received_secret, expected_secret):
        logger.warning("Invalid webhook secret")
        return WebhookSecurityResult(
            is_valid=False,
            error_message="Invalid webhook secret",
            http_status_code=403,
        )

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)


async def verify_webhook_security(
    message_id: str,
    timestamp_str: str,
    phone_number: str,
    received_secret: str | None = None,
    expected_secret: str | None = None,
) -> WebhookSecurityResult:
    """Perform all webhook security validations.

    Args:
        message_id: Unique message ID
        timestamp_str: Unix timestamp string
        phone_number: Phone number making the request
        received_secret: Secret received in request header
        expected_secret: Secret configured in settings

    Returns:
        WebhookSecurityResult with validation result
    """
    # 1. Authentication Check (First line of defense)
    secret_result = await validate_webhook_secret(received_secret, expected_secret)
    if not secret_result.is_valid:
        return secret_result

    # 2. Replay Protection (Timestamp)
    timestamp_result = await validate_webhook_timestamp(timestamp_str)
    if not timestamp_result.is_valid:
        return timestamp_result

    # 3. Replay Protection (Nonce)
    nonce_result = await validate_webhook_nonce(message_id)
    if not nonce_result.is_valid:
        return nonce_result

    # 4. Rate Limiting
    rate_limit_result = await validate_webhook_rate_limit(phone_number)
    if not rate_limit_result.is_valid:
        return rate_limit_result

    return WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)
