"""Webhook authenticity checks via HMAC-SHA256 signature validation."""

from __future__ import annotations

import hashlib
import hmac


def validate_webhook(body: bytes, signature: str, secret: str) -> bool:
    """Compare the WAHA webhook signature against HMAC digests (SHA256 or SHA512)."""
    if not signature:
        return False

    # Try SHA256 (common for X-WAHA-Signature-256)
    expected_sha256 = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if hmac.compare_digest(expected_sha256, signature):
        return True

    # Try SHA512 (default for newer WAHA X-Webhook-Hmac)
    expected_sha512 = hmac.new(
        secret.encode(),
        body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected_sha512, signature)
