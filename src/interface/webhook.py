"""WhatsApp webhook endpoints with signature verification."""

import logging
from datetime import datetime
from typing import Any

import logfire
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pocketbase import PocketBase
from twilio.request_validator import RequestValidator

from src.agents import choresir_agent
from src.agents.base import Deps
from src.core import admin_notifier, db_client
from src.core.config import Constants, settings
from src.core.errors import classify_agent_error, classify_error_with_response
from src.core.rate_limiter import RateLimitExceeded, rate_limiter
from src.domain.user import UserStatus
from src.interface import webhook_security, whatsapp_parser, whatsapp_sender


router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = logging.getLogger(__name__)

# Error messages
ERROR_MSG_BUTTON_PROCESSING_FAILED = (
    "Sorry, I couldn't process that button click. Please try typing your response instead."
)


def verify_twilio_signature(url: str, params: dict[str, str], signature: str) -> bool:
    """Verify Twilio webhook signature.

    Args:
        url: The full URL of the webhook endpoint
        params: Form parameters from the webhook request
        signature: X-Twilio-Signature header value

    Returns:
        True if signature is valid, False otherwise
    """
    auth_token = settings.require_credential("twilio_auth_token", "Twilio Auth Token")
    validator = RequestValidator(auth_token)
    return validator.validate(url, params, signature)


@router.post("")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Receive and validate Twilio webhook POST requests.

    This endpoint:
    1. Validates the X-Twilio-Signature header
    2. Performs security checks (timestamp, nonce, rate limit)
    3. Returns 200 OK immediately
    4. Dispatches message processing to background tasks

    Args:
        request: FastAPI request object containing headers and form data
        background_tasks: FastAPI BackgroundTasks for async processing

    Returns:
        Success status dictionary

    Raises:
        HTTPException: If signature validation or security checks fail
    """
    # Check global webhook rate limit
    try:
        await rate_limiter.check_webhook_rate_limit()
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={
                "Retry-After": str(e.retry_after),
                "X-RateLimit-Limit": str(e.limit),
            },
        ) from e

    # Get form data (not JSON)
    form_data = await request.form()
    params = {k: str(v) for k, v in form_data.items()}

    # Get signature
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    # Build full URL for validation
    url = str(request.url)

    # Verify signature
    if not verify_twilio_signature(url, params, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse message for security validation
    message = whatsapp_parser.parse_twilio_webhook(params)
    if not message:
        logger.warning("Failed to parse webhook for security validation")
        raise HTTPException(status_code=400, detail="Invalid webhook format")

    # Perform security checks (replay attack protection)
    security_result = await webhook_security.verify_webhook_security(
        message_id=message.message_id,
        timestamp_str=message.timestamp,
        phone_number=message.from_phone,
    )

    if not security_result.is_valid:
        logfire.warning(
            f"Webhook security check failed: {security_result.error_message}",
            message_id=message.message_id,
            phone=message.from_phone,
            reason=security_result.error_message,
        )
        raise HTTPException(
            status_code=security_result.http_status_code or 400,
            detail=security_result.error_message,
        )

    # Dispatch to background task
    background_tasks.add_task(process_webhook_message, params)

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
        logger.info(f"Pending user {message.from_phone} sent message")
        response = await choresir_agent.handle_pending_user(user_name=user_record["name"])
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return (result.success, result.error)

    if status == UserStatus.BANNED:
        logger.info(f"Banned user {message.from_phone} sent message")
        response = await choresir_agent.handle_banned_user(user_name=user_record["name"])
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        return (result.success, result.error)

    if status == UserStatus.ACTIVE:
        logger.info(f"Processing active user {message.from_phone} message with agent")

        # Check per-user agent call rate limit
        try:
            await rate_limiter.check_agent_rate_limit(message.from_phone)
        except RateLimitExceeded as e:
            response = (
                f"You've reached your hourly limit of {e.limit} messages. "
                f"Please try again in {e.retry_after // 60} minutes."
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
            logger.error(f"Failed to send response to {message.from_phone}: {result.error}")
        else:
            logger.info(f"Successfully processed message for {message.from_phone}")
        return (result.success, result.error)

    logger.info(f"User {message.from_phone} has unknown status: {status}")
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
        logger.error(f"Record not found for button payload: {e}")
        await whatsapp_sender.send_text_message(
            to_phone=message.from_phone,
            text="This verification request may have expired or been processed already.",
        )
        return (False, str(e))

    except Exception as e:
        # Log with more detail for unexpected exceptions
        logger.error(
            f"Unexpected button handler error ({type(e).__name__}): {e}",
            exc_info=True,  # Include stack trace
        )
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
        filter_query=f'message_id = "{message_id}"',
    )
    if existing_log:
        logger.info(f"Message {message_id} already processed, skipping")
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

    logger.info(f"Processing button click from {message.from_phone}: {message.button_payload}")
    await _log_message_start(message, "Button")

    user_record = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{message.from_phone}"',
    )
    if not user_record:
        logger.warning(f"Unknown user clicked button: {message.from_phone}")
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

    logger.info(f"Processing message from {message.from_phone}: {message.text}")
    await _log_message_start(message, "Processing")

    db = db_client.get_client()
    deps = await choresir_agent.build_deps(db=db, user_phone=message.from_phone)

    if deps is None:
        logger.info(f"Unknown user {message.from_phone}, processing unknown user message")
        response = await choresir_agent.handle_unknown_user(
            user_phone=message.from_phone, message_text=message.text or ""
        )
        result = await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=response)
        await _update_message_status(message_id=message.message_id, success=result.success, error=result.error)
        return

    user_record = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{message.from_phone}"',
    )
    if not user_record:
        logger.error(f"User record not found after build_deps succeeded for {message.from_phone}")
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


async def _handle_webhook_error(e: Exception, params: dict[str, str]) -> None:
    """Handle errors during webhook processing.

    Args:
        e: Exception that occurred
        params: Original webhook parameters
    """
    logger.error(f"Error processing webhook message: {e}")

    error_category, _ = classify_agent_error(e)
    error_response = classify_error_with_response(e)

    logger.error(
        f"Error code: {error_response.code}",
        extra={
            "error_code": error_response.code,
            "severity": error_response.severity.value,
            "error_message": error_response.message,
        },
    )

    if admin_notifier.should_notify_admins(error_category):
        try:
            parsed_message = whatsapp_parser.parse_twilio_webhook(params)
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
        except Exception as notify_error:
            logger.error(f"Failed to notify admins of critical error: {notify_error}")

    try:
        parsed_message = whatsapp_parser.parse_twilio_webhook(params)
        if parsed_message and parsed_message.from_phone:
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
                logger.error(f"Failed to update processed message record: {update_error}")

            user_message = f"{error_response.message}\n\n{error_response.suggestion}"
            await whatsapp_sender.send_text_message(
                to_phone=parsed_message.from_phone,
                text=user_message,
            )
    except Exception as send_error:
        logger.error(f"Failed to send error message to user: {send_error}")


async def process_webhook_message(params: dict[str, str]) -> None:
    """Process Twilio webhook message in background.

    Args:
        params: Form parameters from Twilio webhook
    """
    try:
        message = whatsapp_parser.parse_twilio_webhook(params)
        if message:
            await _route_webhook_message(message)
    except Exception as e:
        await _handle_webhook_error(e, params)
