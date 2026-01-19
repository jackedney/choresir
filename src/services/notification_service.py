"""Notification service for sending WhatsApp messages to household members."""

import logging

from pydantic import ValidationError

from src.core import db_client
from src.core.config import Constants, settings
from src.core.logging import span
from src.domain.user import UserStatus
from src.interface import whatsapp_sender, whatsapp_templates
from src.models.service_models import NotificationResult


logger = logging.getLogger(__name__)


async def send_verification_request(
    *,
    log_id: str,
    chore_id: str,
    claimer_user_id: str,
) -> list[NotificationResult]:
    """Send verification request to all household members except claimer.

    Sends interactive message with Approve/Reject buttons.

    Args:
        log_id: Log record ID (used in button payload)
        chore_id: Chore ID
        claimer_user_id: User who claimed completion (excluded from notifications)

    Returns:
        List of NotificationResult objects with send status
    """
    with span("notification_service.send_verification_request"):
        logger.info(
            "Sending verification request for log_id=%s chore_id=%s claimer=%s",
            log_id,
            chore_id,
            claimer_user_id,
        )

        # 1. Get chore details
        try:
            chore = await db_client.get_record(collection="chores", record_id=chore_id)
            chore_title = chore["title"]
        except KeyError:
            logger.error("Chore not found: %s", chore_id)
            return []

        # 2. Get claimer name
        try:
            claimer = await db_client.get_record(collection="users", record_id=claimer_user_id)
            claimer_name = claimer.get("name", "Someone")
        except KeyError:
            logger.error("Claimer user not found: %s", claimer_user_id)
            claimer_name = "Someone"

        # 3. Get all active users except claimer
        # Note: Using f-string is safe here because UserStatus.ACTIVE is a controlled enum value,
        # not user input. PocketBase also provides additional query sanitization.
        all_users = await db_client.list_records(
            collection="users",
            filter_query=f'status="{UserStatus.ACTIVE}"',
            per_page=Constants.DEFAULT_PER_PAGE_LIMIT,
        )

        # Filter out the claimer
        target_users = [user for user in all_users if user["id"] != claimer_user_id]

        if not target_users:
            logger.warning("No users to notify for verification request")
            return []

        # 4. Send verification message to each user
        results = []
        for user in target_users:
            user_id = user["id"]
            phone = user["phone"]

            send_result = await _send_verification_message(
                to_phone=phone,
                claimer_name=claimer_name,
                chore_title=chore_title,
                log_id=log_id,
            )

            try:
                notification_result = NotificationResult(
                    user_id=user_id,
                    phone=phone,
                    success=send_result.success,
                    error=send_result.error,
                )
                results.append(notification_result)
            except ValidationError as e:
                logger.error("Failed to create NotificationResult for user %s: %s", user_id, e)
                continue

            if send_result.success:
                logger.info("Verification request sent to user=%s phone=%s", user_id, phone)
            else:
                logger.error(
                    "Failed to send verification request to user=%s phone=%s error=%s",
                    user_id,
                    phone,
                    send_result.error,
                )

        # 5. Return results
        logger.info(
            "Sent %d verification requests (%d successful, %d failed)",
            len(results),
            sum(1 for r in results if r.success),
            sum(1 for r in results if not r.success),
        )
        return results


async def _send_verification_message(
    *,
    to_phone: str,
    claimer_name: str,
    chore_title: str,
    log_id: str,
) -> whatsapp_sender.SendMessageResult:
    """Send verification message with interactive buttons.

    Uses Content API template if configured, falls back to text message.

    Args:
        to_phone: Recipient phone number in E.164 format
        claimer_name: Name of user who claimed the chore
        chore_title: Title of the chore to verify
        log_id: Log record ID for button payload

    Returns:
        SendMessageResult indicating success or failure
    """
    # Check if template is configured
    if settings.template_verification_request_sid:
        # Use template message with interactive buttons
        logger.debug("Sending template verification message to %s", to_phone)
        return await whatsapp_templates.send_template_message(
            to_phone=to_phone,
            content_sid=settings.template_verification_request_sid,
            variables={"1": claimer_name, "2": chore_title, "3": log_id},
        )
    # Fallback to plain text message
    logger.debug("Sending text verification message to %s (no template configured)", to_phone)

    # NOTE: This fallback uses simple command format that the AI agent parses.
    # The agent's tool_verify_chore (in src/agents/tools/verification_tools.py) expects:
    # - log_id: Log ID to verify
    # - decision: "APPROVE" or "REJECT"
    # The agent should understand natural language like "approve <log_id>" and "reject <log_id>"
    # and convert them to appropriate tool calls. If the agent's parsing logic changes,
    # this message format should be updated accordingly.
    text = (
        f"✅ {claimer_name} claims they completed *{chore_title}*. "
        f"Can you verify this?\n\n"
        f"Reply 'approve {log_id}' to approve or 'reject {log_id}' to reject."
    )
    return await whatsapp_sender.send_text_message(
        to_phone=to_phone,
        text=text,
    )


async def send_personal_verification_request(
    *,
    log_id: str,
    chore_title: str,
    owner_name: str,
    partner_phone: str,
) -> None:
    """Send accountability partner notification for personal chore verification.

    Args:
        log_id: Personal chore log ID
        chore_title: Personal chore title
        owner_name: Owner's display name
        partner_phone: Accountability partner's phone number

    Raises:
        Exception: If notification fails (logged but not raised)
    """
    try:
        # Build notification message
        message = (
            f"💪 Verification Request\n\n"
            f"{owner_name} claims they completed their personal chore: '{chore_title}'\n\n"
            f"Verify? Reply:\n"
            f"'/personal verify {log_id} approve' to approve\n"
            f"'/personal verify {log_id} reject' to reject"
        )

        # Send DM to accountability partner
        result = await whatsapp_sender.send_text_message(
            to_phone=partner_phone,
            text=message,
        )

        if result.success:
            logger.info("Sent personal verification request to %s for chore '%s'", partner_phone, chore_title)
        else:
            logger.error("Failed to send personal verification request: %s", result.error)

    except Exception:
        logger.exception("Error sending personal verification request for chore '%s'", chore_title)
        # Don't raise - notification failure shouldn't fail the claim


async def send_personal_verification_result(
    *,
    chore_title: str,
    owner_phone: str,
    verifier_name: str,
    approved: bool,
    feedback: str = "",
) -> None:
    """Notify user when their personal chore is verified/rejected.

    Args:
        chore_title: Personal chore title
        owner_phone: Owner's phone number
        verifier_name: Verifier's display name
        approved: True if approved, False if rejected
        feedback: Optional feedback from verifier

    Raises:
        Exception: If notification fails (logged but not raised)
    """
    try:
        # Build notification message
        if approved:
            emoji = "✅"
            status = "approved"
            message = f"{emoji} Personal Chore Verified\n\n{verifier_name} verified your '{chore_title}'! Keep it up!"
        else:
            emoji = "❌"
            status = "rejected"
            message = f"{emoji} Personal Chore Rejected\n\n{verifier_name} rejected your '{chore_title}'."

        if feedback:
            message += f"\n\nFeedback: {feedback}"

        # Send DM to owner
        result = await whatsapp_sender.send_text_message(
            to_phone=owner_phone,
            text=message,
        )

        if result.success:
            logger.info("Sent personal verification result to %s: %s", owner_phone, status)
        else:
            logger.error("Failed to send personal verification result: %s", result.error)

    except Exception:
        logger.exception("Error sending personal verification result for chore '%s'", chore_title)
        # Don't raise - notification failure shouldn't fail the verification
