"""WhatsApp webhook endpoints with signature verification."""

import hashlib
import hmac
from datetime import datetime
from typing import Any

import logfire
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pocketbase import PocketBase

from src.agents import choresir_agent
from src.agents.base import Deps
from src.core import db_client
from src.core.config import settings
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
    logfire.info("POST /webhook - Received webhook request")

    # Get raw body for signature verification
    body = await request.body()
    logfire.info(f"POST /webhook - Body length: {len(body)} bytes")

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


async def _update_message_status(*, message_id: str, success: bool, error: str | None = None) -> None:
    """Update the processed message status in the database.

    Args:
        message_id: WhatsApp message ID
        success: Whether the message was successfully processed
        error: Error message if processing failed
    """
    msg_record = await db_client.get_first_record(
        collection="processed_messages",
        filter_query=f'message_id = "{message_id}"',
    )
    if msg_record:
        await db_client.update_record(
            collection="processed_messages",
            record_id=msg_record["id"],
            data={
                "success": success,
                "error_message": error if not success else None,
            },
        )


async def _handle_user_status(
    *,
    user_record: dict[str, Any],
    message: whatsapp_parser.ParsedMessage,
    db: PocketBase,
    deps: Deps,
) -> tuple[bool, str | None]:
    """Handle message based on user status.

    Returns:
        Tuple of (success: bool, error_message: str | None)
    """
    status = user_record["status"]

    if status == UserStatus.PENDING:
        logfire.info(f"Pending user {message.from_phone} sent message")
        response = await choresir_agent.handle_pending_user(user_name=user_record["name"])
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return (result.success, result.error)

    if status == UserStatus.BANNED:
        logfire.info(f"Banned user {message.from_phone} sent message")
        response = await choresir_agent.handle_banned_user(user_name=user_record["name"])
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return (result.success, result.error)

    if status == UserStatus.ACTIVE:
        logfire.info(f"Processing active user {message.from_phone} message with agent")
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
            logfire.error(f"Failed to send response to {message.from_phone}: {result.error}")
        else:
            logfire.info(f"Successfully processed message for {message.from_phone}")
        return (result.success, result.error)

    logfire.info(f"User {message.from_phone} has unknown status: {status}")
    return (False, f"Unknown user status: {status}")


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
            logfire.info("No text message found in webhook payload, skipping")
            return

        # Check for duplicate message processing
        existing_log = await db_client.get_first_record(
            collection="processed_messages",
            filter_query=f'message_id = "{message.message_id}"',
        )
        if existing_log:
            logfire.info(f"Message {message.message_id} already processed, skipping")
            return

        logfire.info(f"Processing message from {message.from_phone}: {message.text}")

        # Log message processing start
        await db_client.create_record(
            collection="processed_messages",
            data={
                "message_id": message.message_id,
                "from_phone": message.from_phone,
                "processed_at": datetime.now().isoformat(),
                "success": False,
                "error_message": "Processing in progress",
            },
        )

        db = db_client.get_client()
        deps = await choresir_agent.build_deps(db=db, user_phone=message.from_phone)

        if deps is None:
            logfire.info(f"Unknown user {message.from_phone}, sending onboarding message")
            response = await choresir_agent.handle_unknown_user(_user_phone=message.from_phone)
            result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
            await _update_message_status(message_id=message.message_id, success=result.success, error=result.error)
            return

        user_record = await db_client.get_first_record(
            collection="users",
            filter_query=f'phone = "{message.from_phone}"',
        )
        if not user_record:
            logfire.error(f"User record not found after build_deps succeeded for {message.from_phone}")
            await _update_message_status(
                message_id=message.message_id,
                success=False,
                error="User record not found after build_deps succeeded",
            )
            return

        success, error = await _handle_user_status(user_record=user_record, message=message, db=db, deps=deps)
        await _update_message_status(message_id=message.message_id, success=success, error=error)

    except Exception as e:
        logfire.error(f"Error processing webhook message: {e}")
        try:
            parsed_message = whatsapp_parser.extract_first_text_message(payload)
            if parsed_message and parsed_message.from_phone:
                # Try to update the processed message record
                try:
                    existing_record = await db_client.get_first_record(
                        collection="processed_messages",
                        filter_query=f'message_id = "{parsed_message.message_id}"',
                    )
                    if existing_record:
                        await db_client.update_record(
                            collection="processed_messages",
                            record_id=existing_record["id"],
                            data={
                                "success": False,
                                "error_message": str(e),
                            },
                        )
                except Exception as update_error:
                    # If we can't update the record, just log and continue
                    logfire.error(f"Failed to update processed message record: {update_error}")

                await whatsapp_sender.send_text_message(
                    to_phone=parsed_message.from_phone,
                    text="Sorry, an error occurred while processing your message. Please try again later.",
                )
        except Exception as send_error:
            logfire.error(f"Failed to send error message to user: {send_error}")
