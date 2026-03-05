"""Webhook authenticity checks via HMAC-SHA256 signature validation."""

from __future__ import annotations

import hashlib
import hmac


def validate_webhook(body: bytes, signature: str, secret: str) -> bool:
    """Compare the WAHA webhook signature against an HMAC-SHA256 digest of the body."""
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
