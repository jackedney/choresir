"""Personal chore service for CRUD operations."""

import logging
from datetime import datetime
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.services.chore_service import _parse_recurrence_for_personal_chore


logger = logging.getLogger(__name__)


async def create_personal_chore(
    *,
    owner_phone: str,
    title: str,
    recurrence: str | None = None,
    accountability_partner_phone: str | None = None,
) -> dict[str, Any]:
    """Create a new personal chore.

    Args:
        owner_phone: Phone number of chore owner (E.164 format)
        title: Chore title (e.g., "Go to gym")
        recurrence: Recurrence string (CRON, "every X days", "every morning", etc.)
        accountability_partner_phone: Optional partner phone for verification

    Returns:
        Created personal chore record

    Raises:
        ValueError: If recurrence format is invalid
        db_client.DatabaseError: If database operation fails
    """
    with span("personal_chore_service.create_personal_chore"):
        # Parse recurrence if provided
        cron_expression = None
        due_date = None

        if recurrence:
            cron_expression, due_date = _parse_recurrence_for_personal_chore(recurrence)

        # Create chore record
        chore_data = {
            "owner_phone": owner_phone,
            "title": title,
            "recurrence": cron_expression or "",  # Empty string if one-time task
            "due_date": due_date.isoformat() if due_date else "",
            "accountability_partner_phone": accountability_partner_phone or "",
            "status": "ACTIVE",
            "created_at": datetime.now().isoformat(),
        }

        record = await db_client.create_record(collection="personal_chores", data=chore_data)

        logger.info(
            "Created personal chore '%s' for %s (partner: %s)",
            title,
            owner_phone,
            accountability_partner_phone or "none",
        )

        return record


async def get_personal_chores(
    *,
    owner_phone: str,
    status: str = "ACTIVE",
) -> list[dict[str, Any]]:
    """Get all personal chores for a user.

    Args:
        owner_phone: Phone number of chore owner
        status: Filter by status (default: ACTIVE)

    Returns:
        List of personal chore records
    """
    with span("personal_chore_service.get_personal_chores"):
        filter_query = f'owner_phone = "{owner_phone}" && status = "{status}"'

        return await db_client.list_records(
            collection="personal_chores",
            filter_query=filter_query,
            sort="+created_at",
        )


async def get_personal_chore_by_id(
    *,
    chore_id: str,
    owner_phone: str,
) -> dict[str, Any]:
    """Get a personal chore by ID with ownership validation.

    Args:
        chore_id: Personal chore ID
        owner_phone: Expected owner phone (for validation)

    Returns:
        Personal chore record

    Raises:
        KeyError: If chore not found
        PermissionError: If chore doesn't belong to owner
    """
    with span("personal_chore_service.get_personal_chore_by_id"):
        record = await db_client.get_record(
            collection="personal_chores",
            record_id=chore_id,
        )

        # Validate ownership
        if record["owner_phone"] != owner_phone:
            raise PermissionError(f"Personal chore {chore_id} does not belong to {owner_phone}")

        return record


async def delete_personal_chore(
    *,
    chore_id: str,
    owner_phone: str,
) -> None:
    """Archive a personal chore (soft delete).

    Args:
        chore_id: Personal chore ID
        owner_phone: Owner phone (for validation)

    Raises:
        KeyError: If chore not found
        PermissionError: If chore doesn't belong to owner
    """
    with span("personal_chore_service.delete_personal_chore"):
        # Validate ownership
        chore = await get_personal_chore_by_id(
            chore_id=chore_id,
            owner_phone=owner_phone,
        )

        # Soft delete by updating status
        await db_client.update_record(
            collection="personal_chores",
            record_id=chore_id,
            data={"status": "ARCHIVED"},
        )

        logger.info("Archived personal chore '%s' for %s", chore["title"], owner_phone)


def fuzzy_match_personal_chore(
    chores: list[dict],
    title_query: str,
) -> dict | None:
    """Fuzzy match a personal chore by title.

    Uses same logic as household chore fuzzy matching:
    1. Exact match (case-insensitive)
    2. Contains match
    3. Partial word match

    Args:
        chores: List of personal chore records
        title_query: User's search query

    Returns:
        Best matching chore or None
    """
    title_lower = title_query.lower().strip()

    # Exact match
    for chore in chores:
        if chore["title"].lower() == title_lower:
            return chore

    # Contains match
    for chore in chores:
        if title_lower in chore["title"].lower():
            return chore

    # Partial word match
    query_words = set(title_lower.split())
    for chore in chores:
        chore_words = set(chore["title"].lower().split())
        if query_words & chore_words:  # Intersection
            return chore

    return None
