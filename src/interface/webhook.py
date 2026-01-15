"""WhatsApp webhook endpoints with signature verification."""

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pocketbase import PocketBase

from src.agents import choresir_agent
from src.agents.base import Deps
from src.core import db_client
from src.core.config import settings
from src.core.logging import log_debug, log_error, log_info, log_warning
from src.domain.user import UserStatus
from src.interface import whatsapp_parser, whatsapp_sender


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
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Receive and validate WhatsApp webhook POST requests.

    This endpoint:
    1. Validates the X-Hub-Signature-256 header
    2. Returns 200 OK immediately (within 3 seconds per WhatsApp requirements)
    3. Dispatches message processing to background tasks

    Args:
        request: FastAPI request object containing headers and body
        background_tasks: FastAPI BackgroundTasks for async processing

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

    # Parse JSON payload
    payload: dict[str, Any] = await request.json()

    # Dispatch to background task for processing
    background_tasks.add_task(process_webhook_message, payload)

    # Return 200 OK immediately (3-second timeout compliance)
    return {"status": "received"}


async def _handle_user_status(
    *,
    user_record: dict[str, Any],
    message: whatsapp_parser.ParsedMessage,
    db: PocketBase,
    deps: Deps,
) -> None:
    """Handle message based on user status."""
    status = user_record["status"]

    if status == UserStatus.PENDING:
        log_info("Pending user %s sent message", message.from_phone)
        response = await choresir_agent.handle_pending_user(user_name=user_record["name"])
        await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return

    if status == UserStatus.BANNED:
        log_info("Banned user %s sent message", message.from_phone)
        response = await choresir_agent.handle_banned_user(user_name=user_record["name"])
        await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return

    if status == UserStatus.ACTIVE:
        log_info("Processing active user %s message with agent", message.from_phone)
        member_list = await choresir_agent.get_member_list(_db=db)
        agent_response = await choresir_agent.run_agent(
            user_message=message.text or "",
            deps=deps,
            member_list=member_list,
        )
        result = await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text=agent_response,
        )
        if not result.success:
            log_error("Failed to send response to %s: %s", message.from_phone, result.error)
        else:
            log_info("Successfully processed message for %s", message.from_phone)
        return

    log_warning("User %s has unknown status: %s", message.from_phone, status)


async def process_webhook_message(payload: dict[str, Any]) -> None:
    """Process WhatsApp webhook message in background.

    This function:
    1. Parses the webhook payload to extract message and user info
    2. Looks up the user in the database
    3. Handles different user states (unknown, pending, banned, active)
    4. For active users, runs the agent and sends response via WhatsApp
    5. Handles errors gracefully and sends error messages to the user

    Args:
        payload: Parsed webhook JSON payload
    """
    try:
        message = whatsapp_parser.extract_first_text_message(payload)
        if not message or not message.text:
            log_info("No text message found in webhook payload, skipping")
            return

        # Check for duplicate message processing
        existing_log = await db_client.get_first_record(
            collection="logs",
            filter_query=f'message_id = "{message.message_id}"',
        )
        if existing_log:
            log_info("Message %s already processed, skipping", message.message_id)
            return

        log_info("Processing message from %s: %s", message.from_phone, message.text)

        db = db_client.get_client()
        deps = await choresir_agent.build_deps(db=db, user_phone=message.from_phone)

        if deps is None:
            log_info("Unknown user %s, sending onboarding message", message.from_phone)
            response = await choresir_agent.handle_unknown_user(_user_phone=message.from_phone)
            await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
            return

        user_record = await db_client.get_first_record(
            collection="users",
            filter_query=f'phone = "{message.from_phone}"',
        )
        if not user_record:
            log_error("User record not found after build_deps succeeded for %s", message.from_phone)
            return

        await _handle_user_status(user_record=user_record, message=message, db=db, deps=deps)

    except Exception as e:
        log_error("Error processing webhook message: %s", e)
        try:
            parsed_message = whatsapp_parser.extract_first_text_message(payload)
            if parsed_message and parsed_message.from_phone:
                await whatsapp_sender.send_text_message(
                    to_phone=parsed_message.from_phone,
                    text="Sorry, an error occurred while processing your message. Please try again later.",
                )
        except Exception as send_error:
            log_error("Failed to send error message to user: %s", send_error)
