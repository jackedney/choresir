"""Notification service for sending WhatsApp messages to household members."""

import logging

from src.core import db_client
from src.core.logging import span
from src.interface import whatsapp_sender
from src.models.service_models import NotificationResult
from src.services import house_config_service


logger = logging.getLogger(__name__)


async def send_verification_request(
    *,
    log_id: str,
    chore_id: str,
    claimer_user_id: str,
) -> list[NotificationResult]:
    """Send verification request to the group chat.

    Args:
        log_id: Log record ID (used in verification)
        chore_id: Chore ID
        claimer_user_id: User who claimed completion

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
            claimer = await db_client.get_record(collection="members", record_id=claimer_user_id)
            claimer_name = claimer.get("name", "Someone")
        except KeyError:
            logger.error("Claimer user not found: %s", claimer_user_id)
            claimer_name = "Someone"

        # 3. Get house config to retrieve group_chat_id
        house_config = await house_config_service.get_house_config()
        group_chat_id = house_config.group_chat_id

        if not group_chat_id:
            logger.warning("No group_chat_id configured - cannot send verification request")
            return []

        # 4. Build message
        text = (
            f"✅ {claimer_name} claims they completed *{chore_title}*. "
            f"Can you verify this?\n\n"
            f"Reply 'approve {log_id}' to approve or 'reject {log_id}' to reject."
        )

        # 5. Send verification message to the group
        send_result = await whatsapp_sender.send_group_message(
            to_group_id=group_chat_id,
            text=text,
        )

        results = []
        if send_result.success:
            logger.info("Verification request sent to group=%s", group_chat_id)
        else:
            logger.error(
                "Failed to send verification request to group=%s error=%s",
                group_chat_id,
                send_result.error,
            )

        return results


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


async def send_deletion_request_notification(
    *,
    log_id: str,
    chore_id: str,
    chore_title: str,
    requester_user_id: str,
) -> list[NotificationResult]:
    """Send deletion request notification to the group chat.

    Args:
        log_id: Log record ID for the deletion request
        chore_id: Chore ID being requested for deletion
        chore_title: Title of the chore
        requester_user_id: User who requested deletion

    Returns:
        List of NotificationResult objects with send status
    """
    with span("notification_service.send_deletion_request_notification"):
        logger.info(
            "Sending deletion request notification for log_id=%s chore_id=%s requester=%s",
            log_id,
            chore_id,
            requester_user_id,
        )

        # Get requester name
        try:
            requester = await db_client.get_record(collection="members", record_id=requester_user_id)
            requester_name = requester.get("name", "Someone")
        except KeyError:
            logger.error("Requester user not found: %s", requester_user_id)
            requester_name = "Someone"

        # Get house config to retrieve group_chat_id
        house_config = await house_config_service.get_house_config()
        group_chat_id = house_config.group_chat_id

        if not group_chat_id:
            logger.warning("No group_chat_id configured - cannot send deletion request notification")
            return []

        # Build message
        text = (
            f"🗑️ {requester_name} wants to remove the chore *{chore_title}*.\n\n"
            f"Reply 'approve deletion {chore_title}' to approve or "
            f"'reject deletion {chore_title}' to reject."
        )

        # Send notification to the group
        send_result = await whatsapp_sender.send_group_message(
            to_group_id=group_chat_id,
            text=text,
        )

        results = []
        if send_result.success:
            logger.info("Deletion request notification sent to group=%s", group_chat_id)
        else:
            logger.error(
                "Failed to send deletion request notification to group=%s error=%s",
                group_chat_id,
                send_result.error,
            )

        return results


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
