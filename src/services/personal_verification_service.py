"""Personal verification service for accountability partner verification."""

import logging
from datetime import datetime, timedelta

from pydantic import ValidationError

from src.core import db_client
from src.core.config import Constants
from src.core.db_client import sanitize_param
from src.core.logging import span
from src.models.service_models import PersonalChoreLog, PersonalChoreStatistics
from src.services import notification_service, personal_chore_service, user_service


logger = logging.getLogger(__name__)


async def log_personal_chore(
    *,
    chore_id: str,
    owner_phone: str,
    notes: str = "",
) -> PersonalChoreLog:
    """Log completion of a personal chore.

    If chore has accountability partner, creates PENDING log.
    If self-verified, creates SELF_VERIFIED log.

    Args:
        chore_id: Personal chore ID
        owner_phone: Owner phone (for validation)
        notes: Optional notes about completion

    Returns:
        Created PersonalChoreLog object

    Raises:
        KeyError: If chore not found
        PermissionError: If chore doesn't belong to owner
    """
    with span("personal_verification_service.log_personal_chore"):
        # Get chore and validate ownership
        chore = await personal_chore_service.get_personal_chore_by_id(
            chore_id=chore_id,
            owner_phone=owner_phone,
        )

        # Determine verification status
        partner_phone = chore.get("accountability_partner_phone", "")

        if partner_phone:
            # Check if partner still exists and is active
            try:
                partner = await user_service.get_user_by_phone(phone=partner_phone)
                if partner and partner.get("status") == "active":
                    verification_status = "PENDING"
                else:
                    # Partner no longer active, auto-convert to self-verified
                    logger.info(
                        "Partner %s inactive for chore %s, auto-converting to self-verified", partner_phone, chore_id
                    )
                    verification_status = "SELF_VERIFIED"
                    partner_phone = ""
            except Exception:
                # Partner not found, auto-convert to self-verified
                logger.warning(
                    "Partner %s not found for chore %s, auto-converting to self-verified", partner_phone, chore_id
                )
                verification_status = "SELF_VERIFIED"
                partner_phone = ""
        else:
            verification_status = "SELF_VERIFIED"

        # Create log entry
        log_data = {
            "personal_chore_id": chore_id,
            "owner_phone": owner_phone,
            "completed_at": datetime.now().isoformat(),
            "verification_status": verification_status,
            "accountability_partner_phone": partner_phone,
            "partner_feedback": "",
            "notes": notes,
        }

        log_record = await db_client.create_record(
            collection="personal_chore_logs",
            data=log_data,
        )

        logger.info("Logged personal chore '%s' for %s (status: %s)", chore["title"], owner_phone, verification_status)

        # Send verification request notification if pending
        if verification_status == "PENDING" and partner_phone:
            try:
                # Get owner details for notification
                owner = await user_service.get_user_by_phone(phone=owner_phone)
                owner_name = owner["name"] if owner else "Someone"

                await notification_service.send_personal_verification_request(
                    log_id=log_record["id"],
                    chore_title=chore["title"],
                    owner_name=owner_name,
                    partner_phone=partner_phone,
                )
            except Exception:
                logger.exception(
                    "Failed to send verification request notification for chore %s",
                    chore_id,
                )

        return PersonalChoreLog(**log_record)


async def verify_personal_chore(
    *,
    log_id: str,
    verifier_phone: str,
    approved: bool,
    feedback: str = "",
) -> PersonalChoreLog:
    """Verify or reject a personal chore completion.

    Args:
        log_id: Personal chore log ID
        verifier_phone: Accountability partner phone
        approved: True to approve, False to reject
        feedback: Optional feedback message

    Returns:
        Updated PersonalChoreLog object

    Raises:
        KeyError: If log not found
        PermissionError: If verifier is not the accountability partner
    """
    with span("personal_verification_service.verify_personal_chore"):
        # Get log record
        log_record = await db_client.get_record(
            collection="personal_chore_logs",
            record_id=log_id,
        )

        # Validate verifier is the accountability partner
        expected_partner = log_record.get("accountability_partner_phone", "")
        if verifier_phone != expected_partner:
            raise PermissionError(f"Only accountability partner {expected_partner} can verify this chore")

        # Validate log is in PENDING state
        if log_record["verification_status"] != "PENDING":
            raise ValueError(f"Cannot verify log in state {log_record['verification_status']}")

        # Update verification status
        new_status = "VERIFIED" if approved else "REJECTED"
        updated_log = await db_client.update_record(
            collection="personal_chore_logs",
            record_id=log_id,
            data={
                "verification_status": new_status,
                "partner_feedback": feedback,
            },
        )

        logger.info("Personal chore log %s %s by %s", log_id, "approved" if approved else "rejected", verifier_phone)

        # Send result notification to owner
        try:
            chore = await db_client.get_record(
                collection="personal_chores",
                record_id=log_record["personal_chore_id"],
            )
            verifier = await user_service.get_user_by_phone(phone=verifier_phone)
            verifier_name = verifier["name"] if verifier else "your accountability partner"

            await notification_service.send_personal_verification_result(
                chore_title=chore["title"],
                owner_phone=log_record["owner_phone"],
                verifier_name=verifier_name,
                approved=approved,
                feedback=feedback,
            )
        except Exception:
            logger.exception(
                "Failed to send verification result notification for log %s",
                log_id,
            )

        return PersonalChoreLog(**updated_log)


async def get_pending_partner_verifications(
    *,
    partner_phone: str,
) -> list[PersonalChoreLog]:
    """Get all pending verifications for an accountability partner.

    Args:
        partner_phone: Accountability partner phone

    Returns:
        List of PersonalChoreLog objects with enriched chore details
    """
    with span("personal_verification_service.get_pending_partner_verifications"):
        filter_query = (
            f'accountability_partner_phone = "{sanitize_param(partner_phone)}" && verification_status = "PENDING"'
        )

        logs = await db_client.list_records(
            collection="personal_chore_logs",
            filter_query=filter_query,
            sort="-completed_at",
        )

        # Enrich with chore details and convert to models
        enriched_logs = []
        for log in logs:
            try:
                chore = await db_client.get_record(
                    collection="personal_chores",
                    record_id=log["personal_chore_id"],
                )
                # Create enriched view with chore details
                enriched_view = dict(log)  # Shallow copy
                enriched_view["chore_title"] = chore["title"]
                enriched_view["owner_phone_display"] = chore["owner_phone"]

                enriched_log = PersonalChoreLog(**enriched_view)
                enriched_logs.append(enriched_log)
            except (KeyError, ValidationError) as e:
                logger.warning("Failed to process log %s: %s", log.get("id"), e)
                continue

        return enriched_logs


async def auto_verify_expired_logs() -> int:
    """Auto-verify personal chore logs pending for > 48 hours.

    This function is called by the scheduler job.

    Returns:
        Number of logs auto-verified
    """
    with span("personal_verification_service.auto_verify_expired_logs"):
        cutoff_time = datetime.now() - timedelta(hours=Constants.AUTO_VERIFY_PENDING_HOURS)
        filter_query = f'verification_status = "PENDING" && completed_at < "{cutoff_time.isoformat()}"'

        expired_logs = await db_client.list_records(
            collection="personal_chore_logs",
            filter_query=filter_query,
        )

        auto_verified_count = 0
        for log in expired_logs:
            try:
                await db_client.update_record(
                    collection="personal_chore_logs",
                    record_id=log["id"],
                    data={
                        "verification_status": "VERIFIED",
                        "partner_feedback": "Auto-verified (partner did not respond within 48 hours)",
                    },
                )
                auto_verified_count += 1
                logger.info("Auto-verified personal chore log %s (48h timeout)", log["id"])

                # Send auto-verify notification to owner
                try:
                    chore = await db_client.get_record(
                        collection="personal_chores",
                        record_id=log["personal_chore_id"],
                    )
                    partner = await user_service.get_user_by_phone(phone=log["accountability_partner_phone"])
                    partner_name = partner["name"] if partner else "your accountability partner"

                    await notification_service.send_personal_verification_result(
                        chore_title=chore["title"],
                        owner_phone=log["owner_phone"],
                        verifier_name=partner_name,
                        approved=True,
                        feedback="Auto-verified (partner did not respond within 48 hours)",
                    )
                except Exception:
                    logger.exception(
                        "Failed to send auto-verify notification for log %s",
                        log["id"],
                    )

            except Exception as e:
                logger.error("Failed to auto-verify log %s: %s", log["id"], e)
                continue

        logger.info("Auto-verified %d personal chore logs", auto_verified_count)
        return auto_verified_count


async def get_personal_stats(
    *,
    owner_phone: str,
    period_days: int = 30,
) -> PersonalChoreStatistics:
    """Get personal chore statistics for a user.

    Args:
        owner_phone: Owner phone
        period_days: Number of days to include (default: 30)

    Returns:
        PersonalChoreStatistics object with user's personal chore metrics
    """
    with span("personal_verification_service.get_personal_stats"):
        # Get all active chores
        active_chores = await personal_chore_service.get_personal_chores(
            owner_phone=owner_phone,
            status="ACTIVE",
        )

        # Get completions in period
        cutoff_time = datetime.now() - timedelta(days=period_days)
        completions_filter = (
            f'owner_phone = "{sanitize_param(owner_phone)}" '
            f'&& completed_at >= "{cutoff_time.isoformat()}" '
            f'&& (verification_status = "SELF_VERIFIED" || verification_status = "VERIFIED")'
        )

        completions = await db_client.list_records(
            collection="personal_chore_logs",
            filter_query=completions_filter,
        )

        # Get pending verifications
        pending_filter = f'owner_phone = "{sanitize_param(owner_phone)}" && verification_status = "PENDING"'

        pending = await db_client.list_records(
            collection="personal_chore_logs",
            filter_query=pending_filter,
        )

        # Calculate completion rate
        total_chores = len(active_chores)
        completions_count = len(completions)
        completion_rate = (completions_count / total_chores * 100) if total_chores > 0 else 0

        return PersonalChoreStatistics(
            total_chores=total_chores,
            completions_this_period=completions_count,
            pending_verifications=len(pending),
            completion_rate=round(completion_rate, 1),
            period_days=period_days,
        )
