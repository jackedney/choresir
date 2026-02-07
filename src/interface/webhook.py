"""WhatsApp webhook endpoints."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pocketbase import PocketBase
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.agents import choresir_agent
from src.agents.base import Deps
from src.core import admin_notifier, db_client
from src.core.config import Constants
from src.core.db_client import sanitize_param
from src.core.errors import classify_agent_error, classify_error_with_response
from src.core.rate_limiter import rate_limiter
from src.domain.user import UserStatus
from src.interface import webhook_security, whatsapp_parser, whatsapp_sender
from src.services.activation_key_service import check_activation_message
from src.services.conversation_context_service import (
    add_assistant_message,
    add_user_message,
)
from src.services.group_context_service import add_group_message
from src.services.house_config_service import (
    clear_activation_key,
    get_house_config,
    set_group_chat_id,
)
from src.services.lid_resolver import resolve_lid_to_phone
from src.services.user_service import (
    create_pending_name_user,
    update_user_name,
    update_user_status,
)


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


async def _get_sender_phone(message: whatsapp_parser.ParsedMessage) -> str | None:
    """Get the actual sender phone number from a message.

    For group messages, returns the actual sender (participant).
    If the participant uses @lid format, attempts to resolve it via WAHA API.
    For individual messages, returns the from_phone.

    Args:
        message: Parsed message

    Returns:
        The sender's phone number in E.164 format, or None if unresolvable
    """
    if message.is_group_message:
        if message.actual_sender_phone:
            return message.actual_sender_phone
        # Try to resolve @lid to phone number
        if message.participant_lid:
            resolved = await resolve_lid_to_phone(message.participant_lid)
            if resolved:
                return resolved
            logger.warning(
                "Could not resolve participant @lid to phone",
                extra={"lid": message.participant_lid, "group_id": message.group_id},
            )
            return None
    return message.from_phone if message.from_phone else None


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


async def _handle_pending_name_user(
    *,
    user_record: dict[str, Any],
    message: whatsapp_parser.ParsedMessage,
) -> tuple[bool, str | None]:
    """Handle a user with pending_name status - they need to provide their name.

    Args:
        user_record: User database record
        message: Parsed message

    Returns:
        Tuple of (success: bool, error_message: str | None)
    """
    name_text = (message.text or "").strip()

    if not name_text:
        response = "Welcome! Please reply with your name to complete registration."
        result = await _send_response(message=message, text=response)
        return (result.success, result.error)

    # Try to use their message as their name
    try:
        await update_user_name(user_id=user_record["id"], name=name_text)
        await update_user_status(user_id=user_record["id"], status=UserStatus.ACTIVE)

        config = await get_house_config()
        response = f"Thanks {name_text}! You're now registered with {config.name}."
        result = await _send_response(message=message, text=response)
        logger.info("User completed registration", extra={"phone": user_record["phone"], "name": name_text})
        return (result.success, result.error)
    except ValueError as e:
        # Name validation failed
        response = f"That name isn't valid: {e}. Please try again with a different name."
        result = await _send_response(message=message, text=response)
        return (result.success, result.error)


async def _build_message_history(message: whatsapp_parser.ParsedMessage) -> list[ModelMessage]:
    """Build message history from a quoted/replied-to message.

    When a user replies to a bot message, we look up the original bot message
    and include it in the message history so the agent has context.

    Args:
        message: Parsed message that may contain a reply_to_message_id

    Returns:
        List of ModelMessage objects for the agent's message_history parameter
    """
    if not message.reply_to_message_id:
        return []

    # Look up the quoted message text
    quoted_text = await whatsapp_sender.get_bot_message_text(message.reply_to_message_id)
    if not quoted_text:
        logger.debug(
            "Could not find quoted message %s in bot_messages",
            message.reply_to_message_id,
        )
        return []

    # Build a simple history: user asked something, bot responded with quoted_text
    # Since we don't know the original user message, we create a synthetic one
    # The important part is that the agent sees the bot's previous response
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="[Previous message from user]")]),
        ModelResponse(parts=[TextPart(content=quoted_text)]),
    ]

    logger.debug(
        "Built message history from quoted message %s",
        message.reply_to_message_id,
    )
    return history


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
    sender_phone = await _get_sender_phone(message)

    if status == UserStatus.PENDING_NAME:
        return await _handle_pending_name_user(user_record=user_record, message=message)

    if status == UserStatus.ACTIVE:
        logger.info("Processing active user %s message with agent", sender_phone)

        # Check per-user agent call rate limit
        # Note: sender_phone is guaranteed to be non-None here because _handle_text_message
        # checks for None before calling this function
        try:
            await rate_limiter.check_agent_rate_limit(sender_phone or "")
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

        # Record user message in conversation context
        # For group messages, use group_context_service for shared history
        # For DM messages, use conversation_context_service (per-user)
        user_text = message.text or ""
        if sender_phone and user_text:
            try:
                if message.is_group_message:
                    await add_group_message(
                        group_id=message.group_id or "",
                        sender_phone=sender_phone,
                        sender_name=user_record["name"],
                        content=user_text,
                        is_bot=False,
                    )
                else:
                    await add_user_message(user_phone=sender_phone, content=user_text)
            except Exception as e:
                logger.warning("Failed to record user message context: %s", e)

        # Build message history from quoted message (if this is a reply)
        message_history = await _build_message_history(message)

        member_list = await choresir_agent.get_member_list(_db=db)
        agent_response = await choresir_agent.run_agent(
            user_message=user_text,
            deps=deps,
            member_list=member_list,
            message_history=message_history if message_history else None,
        )

        # Record assistant response in conversation context
        # For group messages, use group_context_service for shared history
        # For DM messages, use conversation_context_service (per-user)
        if sender_phone and agent_response:
            try:
                if message.is_group_message:
                    await add_group_message(
                        group_id=message.group_id or "",
                        sender_phone=sender_phone,
                        sender_name=user_record["name"],
                        content=agent_response,
                        is_bot=True,
                    )
                else:
                    await add_assistant_message(user_phone=sender_phone, content=agent_response)
            except Exception as e:
                logger.warning("Failed to record assistant message context: %s", e)

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


async def _log_message_start(
    message: whatsapp_parser.ParsedMessage,
    message_type: str,
    sender_phone: str | None = None,
) -> None:
    """Log the start of message processing.

    Args:
        message: Parsed message
        message_type: Type description for logging
        sender_phone: Resolved sender phone (use if from_phone is empty)
    """
    phone = sender_phone or message.from_phone
    if not phone:
        # Can't log without a phone - skip creating the record
        logger.debug("Skipping processed_messages log - no phone available")
        return

    await db_client.create_record(
        collection="processed_messages",
        data={
            "message_id": message.message_id,
            "from_phone": phone,
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

    sender_phone = await _get_sender_phone(message)

    # Skip messages where we can't determine a valid phone number
    if not sender_phone:
        logger.debug("Skipping button click - no valid sender phone number")
        return

    logger.info("Processing button click from %s: %s", sender_phone, message.button_payload)
    await _log_message_start(message, "Button", sender_phone)

    user_record = await db_client.get_first_record(
        collection="members",
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


async def _handle_new_group_user(*, message: whatsapp_parser.ParsedMessage, sender_phone: str) -> None:
    """Handle a new user messaging in the activated group - auto-register them.

    Args:
        message: Parsed message
        sender_phone: Phone number of the sender
    """
    try:
        await create_pending_name_user(phone=sender_phone)
        logger.info("Auto-registered new group user", extra={"phone": sender_phone})

        # Send prompt asking for their name
        response = "Welcome! Please reply with your name to complete registration."
        await _send_response(message=message, text=response)

        # Log message processing
        await _log_message_start(message, "New user registration", sender_phone)
        await _update_message_status(message_id=message.message_id, success=True)
    except ValueError as e:
        # User already exists - this shouldn't happen but handle gracefully
        logger.warning("Failed to create user during auto-registration: %s", e)


async def _handle_text_message(message: whatsapp_parser.ParsedMessage) -> None:
    """Handle text messages through the agent.

    Args:
        message: Parsed message with text content
    """
    if await _check_duplicate_message(message.message_id):
        return

    # Get the actual sender phone (handles group messages and @lid resolution)
    sender_phone = await _get_sender_phone(message)

    # Skip messages where we can't determine a valid phone number
    # (e.g., WhatsApp linked IDs that couldn't be resolved)
    if not sender_phone:
        logger.debug("Skipping message - no valid sender phone number")
        return

    logger.info("Processing message from %s: %s", sender_phone, message.text)
    await _log_message_start(message, "Processing", sender_phone)

    db = db_client.get_client()
    deps = await choresir_agent.build_deps(db=db, user_phone=sender_phone)

    if deps is None:
        # Unknown user - if this is a group message from the configured group, auto-register
        config = await get_house_config()
        if message.is_group_message and config.group_chat_id and message.group_id == config.group_chat_id:
            await _handle_new_group_user(message=message, sender_phone=sender_phone)
            return

        # Unknown user not in configured group
        logger.info("Unknown user %s, ignoring", sender_phone)
        response = "You are not a member of this household. Please contact an admin."
        result = await _send_response(message=message, text=response)
        await _update_message_status(message_id=message.message_id, success=result.success, error=result.error)
        return

    user_record = await db_client.get_first_record(
        collection="members",
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


async def _activate_group(group_id: str, message: whatsapp_parser.ParsedMessage) -> None:
    """Activate a group as the house group chat.

    Args:
        group_id: The WhatsApp group ID
        message: The message that triggered activation
    """
    # Save group_chat_id to house_config
    success = await set_group_chat_id(group_id)
    if not success:
        logger.error("Failed to set group_chat_id during activation", extra={"group_id": group_id})
        await _send_response(message=message, text="Failed to activate group. Please try again.")
        return

    # Clear the activation key
    await clear_activation_key()

    # Get house name for welcome message
    config = await get_house_config()

    # Send welcome message
    response = (
        f"This group is now activated for {config.name}!\n\n"
        "Everyone who messages here will be automatically registered. "
        "New users just need to reply with their name to complete registration."
    )
    await _send_response(message=message, text=response)

    logger.info("Group activated", extra={"group_id": group_id, "house_name": config.name})


async def _should_process_message(message: whatsapp_parser.ParsedMessage) -> bool:
    """Determine if a message should be processed based on group configuration.

    Behavior:
    - Check for activation key match first (for group activation)
    - Group configured: Process ONLY messages from the configured group, ignore DMs
    - No group configured: Ignore all messages (need to activate first)

    Args:
        message: Parsed message

    Returns:
        True if the message should be processed, False otherwise
    """
    config = await get_house_config()

    # Check for activation key match (group activation flow)
    if (
        message.is_group_message
        and message.group_id
        and config.activation_key
        and message.text
        and check_activation_message(message.text, config.activation_key)
    ):
        logger.info(
            "Activation key matched",
            extra={"group_id": message.group_id, "key": config.activation_key},
        )
        await _activate_group(message.group_id, message)
        # Return False because we've already handled this message
        return False

    if message.is_group_message:
        if not config.group_chat_id:
            # No group configured yet - ignore (user needs to activate first)
            logger.debug(
                "Ignoring group message - no group configured",
                extra={"group_id": message.group_id},
            )
            return False

        if message.group_id != config.group_chat_id:
            logger.debug(
                "Ignoring message from non-configured group",
                extra={"group_id": message.group_id, "configured_group": config.group_chat_id},
            )
            return False

        # Message is from the configured group - process it
        return True

    # Individual message (DM) - ignore in this new flow
    # The bot only works in the configured group
    if config.group_chat_id:
        logger.debug(
            "Ignoring DM - group mode is enabled",
            extra={"from_phone": message.from_phone, "configured_group": config.group_chat_id},
        )
        return False

    # No group configured - ignore DMs too (need activation first)
    logger.debug(
        "Ignoring DM - no group configured",
        extra={"from_phone": message.from_phone},
    )
    return False


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
                f"Webhook error: {error_response.code}\n"
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
