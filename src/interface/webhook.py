"""WhatsApp webhook endpoints."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pocketbase import PocketBase

from src.agents import choresir_agent
from src.agents.base import Deps
from src.core import admin_notifier, db_client
from src.core.config import Constants, settings
from src.core.db_client import sanitize_param
from src.core.errors import classify_agent_error, classify_error_with_response
from src.core.rate_limiter import rate_limiter
from src.domain.user import UserStatus
from src.interface import webhook_security, whatsapp_parser, whatsapp_sender


router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = logging.getLogger(__name__)

# Error messages
ERROR_MSG_BUTTON_PROCESSING_FAILED = (
    "Sorry, I couldn't process that button click. Please try typing your response instead."
)


@router.post("")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Receive and validate WAHA webhook POST requests.

    This endpoint:
    1. Validates HMAC signature before any processing
    2. Parses JSON payload
    3. Performs security checks (timestamp, nonce, rate limit)
    4. Returns 200 OK immediately
    5. Dispatches message processing to background tasks

    Args:
        request: FastAPI request object containing JSON data
        background_tasks: FastAPI BackgroundTasks for async processing

    Returns:
        Success status dictionary

    Raises:
        HTTPException: If payload is invalid or security checks fail
    """
    # Read raw body for HMAC validation before JSON parsing
    raw_body = await request.body()

    # Extract HMAC signature from header
    hmac_signature = request.headers.get("X-Webhook-Hmac")

    # Validate HMAC signature before any other processing
    # This is safe because startup validation ensures waha_webhook_hmac_key is set
    hmac_secret = settings.waha_webhook_hmac_key or ""
    hmac_result = webhook_security.validate_webhook_hmac(
        raw_body=raw_body, signature=hmac_signature, secret=hmac_secret
    )

    if not hmac_result.is_valid:
        logger.warning(
            "HMAC validation failed",
            extra={"operation": "hmac_validation_failed"},
        )
        raise HTTPException(
            status_code=hmac_result.http_status_code or 401,
            detail=hmac_result.error_message,
        )

    # Check global webhook rate limit (raises HTTPException directly)
    await rate_limiter.check_webhook_rate_limit()

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    # Parse message for security validation
    try:
        message = whatsapp_parser.parse_waha_webhook(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not message:
        # Ignore non-message events (e.g., status updates, qr codes)
        return {"status": "ignored"}

    # Perform security checks (replay attack protection)
    # Note: WAHA timestamp might be slightly different or missing in some events,
    # but our parser extracts it.
    security_result = await webhook_security.verify_webhook_security(
        message_id=message.message_id,
        timestamp_str=message.timestamp,
        phone_number=message.from_phone,
    )

    if not security_result.is_valid:
        logger.warning(
            "Webhook security check failed: %s",
            security_result.error_message,
            extra={
                "message_id": message.message_id,
                "reason": security_result.error_message,
            },
        )
        raise HTTPException(
            status_code=security_result.http_status_code or 400,
            detail=security_result.error_message,
        )

    # Dispatch to background task
    background_tasks.add_task(process_webhook_message, payload)

    return {"status": "received"}


async def _update_message_status(*, message_id: str, success: bool, error: str | None = None) -> None:
    """Update the processed message status in the database.

    Args:
        message_id: WhatsApp message ID
        success: Whether the message was successfully processed
        error: Error message if processing failed
    """
    await db_client.update_first_matching(
        collection="processed_messages",
        filter_query=f'message_id = "{sanitize_param(message_id)}"',
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
        logger.info("Pending user sent message", extra={"user_status": "pending"})
        response = await choresir_agent.handle_pending_user(user_name=user_record["name"])
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return (result.success, result.error)

    if status == UserStatus.BANNED:
        logger.info("Banned user sent message", extra={"user_status": "banned"})
        response = await choresir_agent.handle_banned_user(user_name=user_record["name"])
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return (result.success, result.error)

    if status == UserStatus.ACTIVE:
        logger.info("Processing active user message with agent", extra={"user_status": "active"})

        # Check per-user agent call rate limit
        try:
            await rate_limiter.check_agent_rate_limit(message.from_phone)
        except HTTPException as e:
            # Extract rate limit info from headers
            retry_after = e.headers.get("Retry-After", "3600") if e.headers else "3600"
            limit = e.headers.get("X-RateLimit-Limit", "unknown") if e.headers else "unknown"
            response = (
                f"You've reached your hourly limit of {limit} messages. "
                f"Please try again in {int(retry_after) // 60} minutes."
            )
            result = await whatsapp_sender.send_text_message(
                to_phone=message.from_phone,
                text=response,
            )
            return (result.success, result.error)

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
            logger.error("Failed to send response", extra={"error": result.error})
        else:
            logger.info("Successfully processed message", extra={"user_status": "active"})
        return (result.success, result.error)

    logger.info("User has unknown status", extra={"user_status": status})
    return (False, f"Unknown user status: {status}")


async def _handle_button_payload(
    *,
    message: whatsapp_parser.ParsedMessage,
    user_record: dict[str, Any],
) -> tuple[bool, str | None]:
    """Handle button click payloads directly (bypasses agent).

    Parses payload format: VERIFY:{APPROVE|REJECT}:{log_id}

    Args:
        message: Parsed message with button_payload
        user_record: User database record

    Returns:
        Tuple of (success, error_message)
    """
    # Local imports to avoid circular dependency
    from src.services import verification_service
    from src.services.verification_service import VerificationDecision

    payload = message.button_payload
    if not payload:
        logger.error("Button payload is missing")
        result = await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text=ERROR_MSG_BUTTON_PROCESSING_FAILED,
        )
        return (False, "Missing button payload")

    # Parse payload: VERIFY:APPROVE:log_id or VERIFY:REJECT:log_id
    parts = payload.split(":")
    if len(parts) != Constants.WEBHOOK_BUTTON_PAYLOAD_PARTS or parts[0] != "VERIFY":
        logger.error(f"Invalid button payload format: {payload}")
        result = await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text=ERROR_MSG_BUTTON_PROCESSING_FAILED,
        )
        return (False, f"Invalid payload format: {payload}")

    _, decision_str, log_id = parts

    # Validate decision type
    if decision_str not in ("APPROVE", "REJECT"):
        logger.error(f"Invalid decision in payload: {decision_str}")
        result = await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text="Sorry, I couldn't process that button click. Please try typing your response instead.",
        )
        return (False, f"Invalid decision: {decision_str}")

    try:
        # Get log record to find chore_id
        log_record = await db_client.get_record(collection="logs", record_id=log_id)
        chore_id = log_record["chore_id"]
        chore = await db_client.get_record(collection="chores", record_id=chore_id)

        # Execute verification
        decision = VerificationDecision(decision_str)
        await verification_service.verify_chore(
            chore_id=chore_id,
            verifier_user_id=user_record["id"],
            decision=decision,
            reason="Via quick reply button",
        )

        # Send confirmation
        if decision == VerificationDecision.APPROVE:
            response = f"Approved! '{chore['title']}' has been marked as completed."
        else:
            response = f"Rejected. '{chore['title']}' has been moved to conflict resolution."

        result = await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text=response,
        )
        return (result.success, result.error)

    except PermissionError:
        await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text="You cannot verify your own chore claim.",
        )
        return (False, "Self-verification attempted")

    except KeyError as e:
        logger.exception("Record not found for button payload")
        await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text="This verification request may have expired or been processed already.",
        )
        return (False, str(e))

    except Exception as e:
        # Log with more detail for unexpected exceptions
        logger.exception("Unexpected button handler error")
        await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text="Sorry, an error occurred while processing your verification.",
        )
        return (False, f"Unexpected error: {type(e).__name__}: {e!s}")


async def _check_duplicate_message(message_id: str) -> bool:
    """Check if message has already been processed.

    Args:
        message_id: WhatsApp message ID

    Returns:
        True if message is a duplicate, False otherwise
    """
    existing_log = await db_client.get_first_record(
        collection="processed_messages",
        filter_query=f'message_id = "{sanitize_param(message_id)}"',
    )
    if existing_log:
        logger.info("Message %s already processed, skipping", message_id)
        return True
    return False


async def _log_message_start(message: whatsapp_parser.ParsedMessage, message_type: str) -> None:
    """Log the start of message processing.

    Args:
        message: Parsed message
        message_type: Type description for logging
    """
    await db_client.create_record(
        collection="processed_messages",
        data={
            "message_id": message.message_id,
            "from_phone": message.from_phone,
            "processed_at": datetime.now().isoformat(),
            "success": False,
            "error_message": f"{message_type} processing started",
        },
    )


async def _handle_button_message(message: whatsapp_parser.ParsedMessage) -> None:
    """Handle button reply messages.

    Args:
        message: Parsed message with button payload
    """
    if await _check_duplicate_message(message.message_id):
        return

    logger.info("Processing button click", extra={"button_payload": message.button_payload})
    await _log_message_start(message, "Button")

    user_record = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(message.from_phone)}"',
    )
    if not user_record:
        logger.warning("Unknown user clicked button", extra={"operation": "button_unknown_user"})
        await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text="Sorry, I don't recognize your number. Please contact your household admin.",
        )
        return

    success, error = await _handle_button_payload(message=message, user_record=user_record)
    await _update_message_status(message_id=message.message_id, success=success, error=error)


async def _handle_text_message(message: whatsapp_parser.ParsedMessage) -> None:
    """Handle text messages through the agent.

    Args:
        message: Parsed message with text content
    """
    if await _check_duplicate_message(message.message_id):
        return

    logger.info("Processing message", extra={"operation": "text_message"})
    await _log_message_start(message, "Processing")

    db = db_client.get_client()
    deps = await choresir_agent.build_deps(db=db, user_phone=message.from_phone)

    if deps is None:
        logger.info("Unknown user, processing unknown user message", extra={"operation": "unknown_user"})
        response = await choresir_agent.handle_unknown_user(
            user_phone=message.from_phone, message_text=message.text or ""
        )
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        await _update_message_status(message_id=message.message_id, success=result.success, error=result.error)
        return

    user_record = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(message.from_phone)}"',
    )
    if not user_record:
        logger.error("User record not found after build_deps succeeded", extra={"operation": "record_not_found"})
        await _update_message_status(
            message_id=message.message_id,
            success=False,
            error="User record not found after build_deps succeeded",
        )
        return

    success, error = await _handle_user_status(user_record=user_record, message=message, db=db, deps=deps)
    await _update_message_status(message_id=message.message_id, success=success, error=error)


async def _route_webhook_message(message: whatsapp_parser.ParsedMessage) -> None:
    """Route message to appropriate handler based on type.

    Args:
        message: Parsed message
    """
    if message.message_type == "button_reply" and message.button_payload:
        await _handle_button_message(message)
    elif message.text:
        await _handle_text_message(message)
    else:
        logger.info("No text message found, skipping")


async def _handle_webhook_error(
    *,
    e: Exception,
    params: dict[str, Any],
    parsed_message: whatsapp_parser.ParsedMessage | None = None,
) -> None:
    """Handle errors during webhook processing.

    Args:
        e: Exception that occurred
        params: Original webhook parameters
        parsed_message: Already parsed message (if available, avoids re-parsing)
    """
    logger.exception("Error processing webhook message")

    error_category, _ = classify_agent_error(e)
    error_response = classify_error_with_response(e)

    logger.error(
        "Error code: %s",
        error_response.code,
        extra={
            "error_code": error_response.code,
            "severity": error_response.severity.value,
            "error_message": error_response.message,
        },
    )

    if admin_notifier.should_notify_admins(error_category):
        try:
            if parsed_message is None:
                parsed_message = whatsapp_parser.parse_waha_webhook(params)
            user_context = "Unknown user"
            if parsed_message and parsed_message.from_phone:
                user_context = parsed_message.from_phone

            timestamp = datetime.now().isoformat()
            error_preview = str(e)[:100]
            notification_msg = (
                f"⚠️ Webhook error: {error_response.code}\n"
                f"Category: {error_category.value}\n"
                f"Severity: {error_response.severity.value}\n"
                f"User: {user_context}\nTime: {timestamp}\nError: {error_preview}"
            )
            await admin_notifier.notify_admins(
                message=notification_msg,
                severity="critical",
            )
        except Exception:
            logger.exception("Failed to notify admins of critical error")

    try:
        if parsed_message and parsed_message.from_phone:
            try:
                await db_client.update_first_matching(
                    collection="processed_messages",
                    filter_query=f'message_id = "{sanitize_param(parsed_message.message_id)}"',
                    data={
                        "success": False,
                        "error_message": str(e),
                    },
                )
            except Exception:
                logger.exception("Failed to update processed message record")

            user_message = f"{error_response.message}\n\n{error_response.suggestion}"
            await whatsapp_sender.send_text_message(
                to_phone=parsed_message.from_phone,
                text=user_message,
            )
    except Exception:
        logger.exception("Failed to send error message to user")


async def process_webhook_message(params: dict[str, Any]) -> None:
    """Process WAHA webhook message in background.

    Args:
        params: JSON payload from WAHA webhook
    """
    message = None
    try:
        message = whatsapp_parser.parse_waha_webhook(params)
        if message:
            await _route_webhook_message(message)
    except Exception as e:
        await _handle_webhook_error(e=e, params=params, parsed_message=message)
