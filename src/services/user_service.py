"""User service for onboarding and member management."""

import logging
from typing import Any

from src.core import db_client
from src.core.db_client import sanitize_param
from src.core.logging import span
from src.domain.create_models import UserCreate
from src.domain.user import User, UserRole, UserStatus


logger = logging.getLogger(__name__)


async def create_pending_name_user(*, phone: str) -> dict[str, Any]:
    """Create a user with pending_name status from group auto-registration.

    The user must reply with their name to become active.

    Args:
        phone: User's phone number in E.164 format

    Returns:
        Created user record

    Raises:
        ValueError: If user already exists
        db_client.DatabaseError: If database operation fails
    """
    with span("user_service.create_pending_name_user"):
        # Guard: Check if user already exists
        existing_user = await db_client.get_first_record(
            collection="members",
            filter_query=f'phone = "{sanitize_param(phone)}"',
        )
        if existing_user:
            msg = f"User with phone {phone} already exists"
            logger.warning(msg)
            raise ValueError(msg)

        user_create = UserCreate(
            phone=phone,
            name="Pending",
            role=UserRole.MEMBER,
            status=UserStatus.PENDING_NAME,
        )

        record = await db_client.create_record(collection="members", data=user_create.model_dump())
        logger.info("Created pending_name user: %s", phone)

        return record


async def update_user_name(*, user_id: str, name: str) -> dict[str, Any]:
    """Update a user's name.

    Args:
        user_id: User's unique ID
        name: New display name

    Returns:
        Updated user record

    Raises:
        ValueError: If name is invalid
        db_client.RecordNotFoundError: If user not found
    """
    with span("user_service.update_user_name"):
        # Validate name using User model validator
        try:
            User(id="temp", phone="+10000000000", name=name)
        except Exception as e:
            msg = str(e)
            logger.warning("Invalid name for user %s: %s", user_id, msg)
            raise ValueError(msg) from e

        updated_record = await db_client.update_record(
            collection="members",
            record_id=user_id,
            data={"name": name.strip()},
        )

        logger.info("Updated name for user %s to: %s", user_id, name)
        return updated_record


async def update_user_status(*, user_id: str, status: UserStatus) -> dict[str, Any]:
    """Update a user's status.

    Args:
        user_id: User's unique ID
        status: New status

    Returns:
        Updated user record

    Raises:
        db_client.RecordNotFoundError: If user not found
    """
    with span("user_service.update_user_status"):
        updated_record = await db_client.update_record(
            collection="members",
            record_id=user_id,
            data={"status": status},
        )

        logger.info("Updated status for user %s to: %s", user_id, status)
        return updated_record


async def approve_member(*, admin_user_id: str, target_phone: str) -> dict[str, Any]:
    """Approve a pending member (admin-only).

    Changes user status from "pending_name" to "active".

    Args:
        admin_user_id: ID of the admin performing the approval
        target_phone: Phone number of the user to approve

    Returns:
        Updated user record

    Raises:
        UnauthorizedError: If requesting user is not an admin
        db_client.RecordNotFoundError: If admin or target user not found
        UserServiceError: If target user is not pending
    """
    with span("user_service.approve_member"):
        # Guard: Verify admin privileges
        admin_record = await db_client.get_record(collection="members", record_id=admin_user_id)
        if admin_record["role"] != UserRole.ADMIN:
            msg = f"User {admin_user_id} is not authorized to approve members"
            logger.warning(msg)
            raise PermissionError(msg)

        # Guard: Find target user
        target_user = await db_client.get_first_record(
            collection="members",
            filter_query=f'phone = "{sanitize_param(target_phone)}"',
        )
        if not target_user:
            msg = f"User with phone {target_phone} not found"
            raise KeyError(msg)

        # Guard: Check user is pending
        if target_user["status"] not in (UserStatus.PENDING_NAME,):
            msg = f"User {target_phone} is not pending approval (status: {target_user['status']})"
            logger.warning(msg)
            raise ValueError(msg)

        # Approve user
        updated_record = await db_client.update_record(
            collection="members",
            record_id=target_user["id"],
            data={"status": UserStatus.ACTIVE},
        )

        logger.info("Approved user %s by admin %s", target_phone, admin_user_id)

        return updated_record


async def remove_user(*, admin_user_id: str, target_user_id: str) -> None:
    """Remove a user (admin-only).

    Deletes the user record from the database.

    Args:
        admin_user_id: ID of the admin performing the removal
        target_user_id: ID of the user to remove

    Raises:
        PermissionError: If requesting user is not an admin
        db_client.RecordNotFoundError: If admin or target user not found
    """
    with span("user_service.remove_user"):
        # Guard: Verify admin privileges
        admin_record = await db_client.get_record(collection="members", record_id=admin_user_id)
        if admin_record["role"] != UserRole.ADMIN:
            msg = f"User {admin_user_id} is not authorized to remove users"
            logger.warning(msg)
            raise PermissionError(msg)

        # Guard: Verify target user exists (will raise if not found)
        await db_client.get_record(collection="members", record_id=target_user_id)

        # Delete user
        await db_client.delete_record(collection="members", record_id=target_user_id)

        logger.info("Removed user %s by admin %s", target_user_id, admin_user_id)


async def get_user_by_phone(*, phone: str) -> dict[str, Any] | None:
    """Get user by phone number.

    Args:
        phone: User's phone number in E.164 format

    Returns:
        User record or None if not found

    Raises:
        db_client.DatabaseError: If database operation fails
    """
    return await db_client.get_first_record(
        collection="members",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )


async def get_user_by_id(*, user_id: str) -> dict[str, Any]:
    """Get user by ID.

    Args:
        user_id: User's unique ID

    Returns:
        User record

    Raises:
        db_client.RecordNotFoundError: If user not found
        db_client.DatabaseError: If database operation fails
    """
    return await db_client.get_record(collection="members", record_id=user_id)
