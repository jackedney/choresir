"""WhatsApp webhook endpoints."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pocketbase import PocketBase

from src.agents import choresir_agent
from src.agents.base import Deps
from src.core import admin_notifier, db_client
from src.core.config import Constants
from src.core.db_client import sanitize_param
from src.core.errors import classify_agent_error, classify_error_with_response
from src.core.rate_limiter import rate_limiter
from src.domain.user import UserStatus
from src.interface import webhook_security, whatsapp_parser, whatsapp_sender
from src.services.house_config_service import get_house_config, set_group_chat_id


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
    1. Parses JSON payload
    2. Performs security checks (timestamp, nonce, rate limit)
    3. Returns 200 OK immediately
    4. Dispatches message processing to background tasks

    Args:
        request: FastAPI request object containing JSON data
        background_tasks: FastAPI BackgroundTasks for async processing

    Returns:
        Success status dictionary

    Raises:
        HTTPException: If payload is invalid or security checks fail
    """
    # Check global webhook rate limit (raises HTTPException directly)
    await rate_limiter.check_webhook_rate_limit()

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    # Parse message for security validation
    message = whatsapp_parser.parse_waha_webhook(payload)
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
        # For duplicates, return 200 to prevent WhatsApp retries
        if security_result.error_message == "Duplicate webhook":
            return {"status": "duplicate"}

        logger.warning(
            "Webhook security check failed: %s",
            security_result.error_message,
            extra={
                "message_id": message.message_id,
                "phone": message.from_phone,
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
    msg_record = await db_client.get_first_record(
        collection="processed_messages",
        filter_query=f'message_id = "{sanitize_param(message_id)}"',
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


def _get_sender_phone(message: whatsapp_parser.ParsedMessage) -> str:
    """Get the actual sender phone number from a message.

    For group messages, returns the actual sender (participant).
    For individual messages, returns the from_phone.

    Args:
        message: Parsed message

    Returns:
        The sender's phone number in E.164 format
    """
    if message.is_group_message and message.actual_sender_phone:
        return message.actual_sender_phone
    return message.from_phone


async def _send_response(*, message: whatsapp_parser.ParsedMessage, text: str) -> whatsapp_sender.SendMessageResult:
    """Send a response to a message, routing to group or individual as appropriate.

    Args:
        message: Original parsed message (determines routing)
        text: Response text to send

    Returns:
        SendMessageResult from the send operation
    """
    if message.is_group_message and message.group_id:
        return await whatsapp_sender.send_group_message(to_group_id=message.group_id, text=text)
    return await whatsapp_sender.send_text_message(to_phone=message.from_phone, text=text)


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
    sender_phone = _get_sender_phone(message)

    if status == UserStatus.PENDING:
        # Check if user has a pending invite (admin-initiated flow)
        pending_invite = await db_client.get_first_record(
            collection="pending_invites",
            filter_query=f'phone = "{db_client.sanitize_param(sender_phone)}"',
        )

        if pending_invite:
            # Handle invite confirmation
            normalized_message = (message.text or "").strip().upper()
            if normalized_message == "YES":
                # Activate user
                await db_client.update_record(
                    collection="users",
                    record_id=user_record["id"],
                    data={"status": UserStatus.ACTIVE},
                )
                logger.info("invite_confirmed", extra={"user_phone": sender_phone})

                # Delete pending invite
                await db_client.delete_record(
                    collection="pending_invites",
                    record_id=pending_invite["id"],
                )

                # Get house name for welcome message
                config = await get_house_config()
                response = f"Welcome to {config.name}! Your membership is now active."
            else:
                response = "To confirm your invitation, please reply YES"

            result = await _send_response(message=message, text=response)
            return (result.success, result.error)

        # No pending invite - user requested to join via WhatsApp
        logger.info("Pending user %s sent message", sender_phone)
        response = await choresir_agent.handle_pending_user(user_name=user_record["name"])
        result = await _send_response(message=message, text=response)
        return (result.success, result.error)

    if status == UserStatus.ACTIVE:
        logger.info("Processing active user %s message with agent", sender_phone)

        # Check per-user agent call rate limit
        try:
            await rate_limiter.check_agent_rate_limit(sender_phone)
        except HTTPException as e:
            # Extract rate limit info from headers
            retry_after = e.headers.get("Retry-After", "3600") if e.headers else "3600"
            limit = e.headers.get("X-RateLimit-Limit", "unknown") if e.headers else "unknown"
            response = (
                f"You've reached your hourly limit of {limit} messages. "
                f"Please try again in {int(retry_after) // 60} minutes."
            )
            result = await _send_response(message=message, text=response)
            return (result.success, result.error)

        member_list = await choresir_agent.get_member_list(_db=db)
        agent_response = await choresir_agent.run_agent(
            user_message=message.text or "",
            deps=deps,
            member_list=member_list,
        )
        result = await _send_response(message=message, text=agent_response)
        if not result.success:
            logger.error("Failed to send response to %s: %s", sender_phone, result.error)
        else:
            logger.info("Successfully processed message for %s", sender_phone)
        return (result.success, result.error)

    logger.info("User %s has unknown status: %s", sender_phone, status)
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
        await _send_response(message=message, text=ERROR_MSG_BUTTON_PROCESSING_FAILED)
        return (False, "Missing button payload")

    # Parse payload: VERIFY:APPROVE:log_id or VERIFY:REJECT:log_id
    parts = payload.split(":")
    if len(parts) != Constants.WEBHOOK_BUTTON_PAYLOAD_PARTS or parts[0] != "VERIFY":
        logger.error("Invalid button payload format: %s", payload)
        await _send_response(message=message, text=ERROR_MSG_BUTTON_PROCESSING_FAILED)
        return (False, f"Invalid payload format: {payload}")

    _, decision_str, log_id = parts

    # Validate decision type
    if decision_str not in ("APPROVE", "REJECT"):
        logger.error("Invalid decision in payload: %s", decision_str)
        await _send_response(
            message=message,
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

        result = await _send_response(message=message, text=response)
        return (result.success, result.error)

    except PermissionError:
        await _send_response(message=message, text="You cannot verify your own chore claim.")
        return (False, "Self-verification attempted")

    except KeyError as e:
        logger.error("Record not found for button payload: %s", e)
        await _send_response(
            message=message,
            text="This verification request may have expired or been processed already.",
        )
        return (False, str(e))

    except Exception as e:
        # Log with more detail for unexpected exceptions
        logger.error(
            "Unexpected button handler error (%s): %s",
            type(e).__name__,
            e,
            exc_info=True,  # Include stack trace
        )
        await _send_response(
            message=message,
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

    sender_phone = _get_sender_phone(message)
    logger.info("Processing button click from %s: %s", sender_phone, message.button_payload)
    await _log_message_start(message, "Button")

    user_record = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(sender_phone)}"',
    )
    if not user_record:
        logger.warning("Unknown user clicked button: %s", sender_phone)
        await _send_response(
            message=message,
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

    # Get the actual sender phone (handles group messages)
    sender_phone = _get_sender_phone(message)

    logger.info("Processing message from %s: %s", sender_phone, message.text)
    await _log_message_start(message, "Processing")

    db = db_client.get_client()
    deps = await choresir_agent.build_deps(db=db, user_phone=sender_phone)

    if deps is None:
        logger.info("Unknown user %s, processing unknown user message", sender_phone)
        response = await choresir_agent.handle_unknown_user(user_phone=sender_phone, message_text=message.text or "")
        result = await _send_response(message=message, text=response)
        await _update_message_status(message_id=message.message_id, success=result.success, error=result.error)
        return

    user_record = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(sender_phone)}"',
    )
    if not user_record:
        logger.error("User record not found after build_deps succeeded for %s", sender_phone)
        await _update_message_status(
            message_id=message.message_id,
            success=False,
            error="User record not found after build_deps succeeded",
        )
        return

    success, error = await _handle_user_status(user_record=user_record, message=message, db=db, deps=deps)
    await _update_message_status(message_id=message.message_id, success=success, error=error)


async def _has_pending_invite(phone: str) -> bool:
    """Check if a phone number has a pending invite.

    Args:
        phone: Phone number in E.164 format

    Returns:
        True if user has a pending invite, False otherwise
    """
    pending_invite = await db_client.get_first_record(
        collection="pending_invites",
        filter_query=f'phone = "{db_client.sanitize_param(phone)}"',
    )
    return pending_invite is not None


async def _should_process_message(message: whatsapp_parser.ParsedMessage) -> bool:
    """Determine if a message should be processed based on group configuration.

    Behavior:
    - No group configured + group message received: Auto-save group ID and process
    - Group configured: Process ONLY messages from the configured group, ignore DMs
    - No group configured + DM: Process DMs (legacy behavior)
    - EXCEPTION: Always process DMs from users with pending invites (for confirmation)

    Args:
        message: Parsed message

    Returns:
        True if the message should be processed, False otherwise
    """
    config = await get_house_config()

    if message.is_group_message:
        if not config.group_chat_id:
            # Auto-detect: First group message sets the house group
            if message.group_id:
                logger.info(
                    "Auto-detecting house group chat",
                    extra={"group_id": message.group_id},
                )
                success = await set_group_chat_id(message.group_id)
                if success:
                    logger.info(
                        "House group chat auto-configured",
                        extra={"group_id": message.group_id},
                    )
                    # Process this message since we just configured this group
                    return True
                logger.warning(
                    "Failed to auto-configure group chat",
                    extra={"group_id": message.group_id},
                )
                return False
            return False

        if message.group_id != config.group_chat_id:
            logger.debug(
                "Ignoring message from non-configured group",
                extra={"group_id": message.group_id, "configured_group": config.group_chat_id},
            )
            return False

        # Message is from the configured group - process it
        return True

    # Individual message (DM)
    if config.group_chat_id:
        # Group is configured - but allow DMs for pending invite confirmations
        if await _has_pending_invite(message.from_phone):
            logger.info(
                "Processing DM from user with pending invite",
                extra={"from_phone": message.from_phone},
            )
            return True

        # Otherwise ignore DMs in group mode
        logger.debug(
            "Ignoring DM - group mode is enabled",
            extra={"from_phone": message.from_phone, "configured_group": config.group_chat_id},
        )
        return False

    # No group configured - process DMs (current behavior)
    return True


async def _route_webhook_message(message: whatsapp_parser.ParsedMessage) -> None:
    """Route message to appropriate handler based on type.

    Args:
        message: Parsed message
    """
    # Check if we should process this message based on group configuration
    if not await _should_process_message(message):
        return

    if message.message_type == "button_reply" and message.button_payload:
        await _handle_button_message(message)
    elif message.text:
        await _handle_text_message(message)
    else:
        logger.info("No text message found, skipping")


async def _handle_webhook_error(e: Exception, params: dict[str, Any]) -> None:
    """Handle errors during webhook processing.

    Args:
        e: Exception that occurred
        params: Original webhook parameters
    """
    logger.error("Error processing webhook message: %s", e)

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
        except Exception as notify_error:
            logger.error("Failed to notify admins of critical error: %s", notify_error)

    try:
        parsed_message = whatsapp_parser.parse_waha_webhook(params)
        if parsed_message and parsed_message.from_phone:
            try:
                existing_record = await db_client.get_first_record(
                    collection="processed_messages",
                    filter_query=f'message_id = "{sanitize_param(parsed_message.message_id)}"',
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
                logger.error("Failed to update processed message record: %s", update_error)

            user_message = f"{error_response.message}\n\n{error_response.suggestion}"
            await whatsapp_sender.send_text_message(
                to_phone=parsed_message.from_phone,
                text=user_message,
            )
    except Exception as send_error:
        logger.error("Failed to send error message to user: %s", send_error)


async def process_webhook_message(params: dict[str, Any]) -> None:
    """Process WAHA webhook message in background.

    Args:
        params: JSON payload from WAHA webhook
    """
    try:
        message = whatsapp_parser.parse_waha_webhook(params)
        if message:
            await _route_webhook_message(message)
    except Exception as e:
        await _handle_webhook_error(e, params)
