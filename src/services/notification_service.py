"""Notification service for sending WhatsApp messages to household members."""

import logging

from src.core import db_client, message_templates
from src.core.logging import span
from src.interface import whatsapp_sender
from src.models.service_models import NotificationResult
from src.services import house_config_service


logger = logging.getLogger(__name__)


async def send_verification_request(
    *,
    log_id: str,
    task_id: str,
    claimer_user_id: str,
) -> list[NotificationResult]:
    """Send verification request to a group chat.

    Args:
        log_id: Log record ID (used in verification)
        task_id: Task ID
        claimer_user_id: User who claimed completion

    Returns:
        List of NotificationResult objects with send status
    """
    with span("notification_service.send_verification_request"):
        logger.info(
            "Sending verification request for log_id=%s task_id=%s claimer=%s",
            log_id,
            task_id,
            claimer_user_id,
        )

        # 1. Get task details
        try:
            task = await db_client.get_record(collection="tasks", record_id=task_id)
            _title = task["title"]
        except KeyError:
            logger.error("Task not found: %s", task_id)
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
        text = message_templates.verification_request(
            claimer_name=claimer_name,
            item_title=_title,
            log_id=log_id,
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
    task_title: str,
    owner_name: str,
    partner_phone: str,
) -> None:
    """Send accountability partner notification for personal task verification.

    Args:
        log_id: Personal task log ID
        task_title: Personal task title
        owner_name: Owner's display name
        partner_phone: Accountability partner's phone number

    Raises:
        Exception: If notification fails (logged but not raised)
    """
    try:
        # Build notification message
        message = message_templates.personal_verification_request(
            owner_name=owner_name,
            item_title=task_title,
            log_id=log_id,
        )

        # Send DM to accountability partner
        result = await whatsapp_sender.send_text_message(
            to_phone=partner_phone,
            text=message,
        )

        if result.success:
            logger.info("Sent personal verification request to %s for task '%s'", partner_phone, task_title)
        else:
            logger.error("Failed to send personal verification request: %s", result.error)

    except Exception:
        logger.exception("Error sending personal verification request for task '%s'", task_title)
        # Don't raise - notification failure shouldn't fail the claim


async def send_deletion_request_notification(
    *,
    log_id: str,
    task_id: str,
    task_title: str,
    requester_user_id: str,
) -> list[NotificationResult]:
    """Send deletion request notification to a group chat.

    Args:
        log_id: Log record ID for deletion request
        task_id: Task ID being requested for deletion
        task_title: Title of the task
        requester_user_id: User who requested deletion

    Returns:
        List of NotificationResult objects with send status
    """
    with span("notification_service.send_deletion_request_notification"):
        logger.info(
            "Sending deletion request notification for log_id=%s task_id=%s requester=%s",
            log_id,
            task_id,
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
        text = message_templates.deletion_request(
            requester_name=requester_name,
            item_title=task_title,
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
    task_title: str,
    owner_phone: str,
    verifier_name: str,
    approved: bool,
    feedback: str = "",
) -> None:
    """Notify user when their personal task is verified/rejected.

    Args:
        task_title: Personal task title
        owner_phone: Owner's phone number
        verifier_name: Verifier's display name
        approved: True if approved, False if rejected
        feedback: Optional feedback from verifier

    Raises:
        Exception: If notification fails (logged but not raised)
    """
    try:
        # Build notification message
        message = message_templates.personal_verification_result(
            item_title=task_title,
            verifier_name=verifier_name,
            approved=approved,
            feedback=feedback,
        )

        # Send DM to owner
        result = await whatsapp_sender.send_text_message(
            to_phone=owner_phone,
            text=message,
        )

        if result.success:
            logger.info("Sent personal verification result to %s for task '%s'", owner_phone, task_title)
        else:
            logger.error("Failed to send personal verification result: %s", result.error)

    except Exception:
        logger.exception("Error sending personal verification result for task '%s'", task_title)
        # Don't raise - notification failure shouldn't fail the verification
