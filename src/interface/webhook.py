"""WhatsApp webhook endpoints with signature verification."""

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from src.core.config import settings


router = APIRouter(prefix="/webhook", tags=["webhook"])


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify WhatsApp webhook signature using HMAC SHA256.

    Args:
        payload: Raw request body bytes
        signature: X-Hub-Signature-256 header value (format: 'sha256=hash')

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature.startswith("sha256="):
        return False

    expected_signature = signature[7:]  # Remove 'sha256=' prefix
    computed_hmac = hmac.new(
        settings.whatsapp_app_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, expected_signature)


@router.get("", response_class=PlainTextResponse)
async def verify_webhook(
    *,
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> str:
    """Handle WhatsApp webhook verification handshake.

    Meta sends a GET request with mode, token, and challenge parameters.
    We verify the token matches our WHATSAPP_VERIFY_TOKEN and return the challenge.

    Args:
        mode: Should be 'subscribe'
        token: Verification token from Meta (must match our configured token)
        challenge: Random string to echo back

    Returns:
        The challenge string if verification succeeds

    Raises:
        HTTPException: If verification fails
    """
    if mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid mode")

    if token != settings.whatsapp_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    return challenge


@router.post("")
async def receive_webhook(request: Request) -> dict[str, str]:
    """Receive and validate WhatsApp webhook POST requests.

    This endpoint:
    1. Validates the X-Hub-Signature-256 header
    2. Returns 200 OK immediately (within 3 seconds per WhatsApp requirements)
    3. Actual message processing happens in background tasks (to be added in Task 23)

    Args:
        request: FastAPI request object containing headers and body

    Returns:
        Success status dictionary

    Raises:
        HTTPException: If signature validation fails
    """
    # Get raw body for signature verification
    body = await request.body()

    # Get signature from header
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    # Verify signature
    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON payload (will be used in Task 23 for background processing)
    _payload: dict[str, Any] = await request.json()

    # Return 200 OK immediately (actual processing will happen in background tasks)
    # Background task integration will be added in Task 23
    return {"status": "received"}
