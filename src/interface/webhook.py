"""WhatsApp webhook endpoints with signature verification."""

from datetime import datetime
from typing import Any

import logfire
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pocketbase import PocketBase
from twilio.request_validator import RequestValidator

from src.agents import choresir_agent
from src.agents.base import Deps
from src.core import db_client
from src.core.config import settings
from src.domain.user import UserStatus
from src.interface import whatsapp_parser, whatsapp_sender


router = APIRouter(prefix="/webhook", tags=["webhook"])


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
    2. Returns 200 OK immediately
    3. Dispatches message processing to background tasks

    Args:
        request: FastAPI request object containing headers and form data
        background_tasks: FastAPI BackgroundTasks for async processing

    Returns:
        Success status dictionary

    Raises:
        HTTPException: If signature validation fails
    """
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


async def process_webhook_message(params: dict[str, str]) -> None:
    """Process Twilio webhook message in background.

    This function:
    1. Parses the webhook params to extract message and user info
    2. Looks up the user in the database
    3. Handles different user states (unknown, pending, banned, active)
    4. For active users, runs the agent and sends response via WhatsApp
    5. Handles errors gracefully and sends error messages to the user

    Args:
        params: Form parameters from Twilio webhook
    """
    try:
        message = whatsapp_parser.parse_twilio_webhook(params)
        if not message or not message.text:
            logfire.info("No text message found, skipping")
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
            logfire.info(f"Unknown user {message.from_phone}, processing unknown user message")
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
            parsed_message = whatsapp_parser.parse_twilio_webhook(params)
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
