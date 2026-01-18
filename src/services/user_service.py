"""User service for onboarding and member management."""

import logging
from typing import Any

from src.core import db_client
from src.core.config import settings
from src.core.logging import span
from src.domain.user import UserRole, UserStatus


logger = logging.getLogger(__name__)


async def request_join(*, phone: str, name: str, house_code: str, password: str) -> dict[str, Any]:
    """Request to join the household.

    Validates house code and password against environment variables.
    Creates user with status="pending" for admin approval.

    Args:
        phone: User's phone number in E.164 format
        name: User's display name
        house_code: House code provided by user
        password: House password provided by user

    Returns:
        Created user record

    Raises:
        ValueError: If house code or password is incorrect
        db_client.DatabaseError: If database operation fails
    """
    with span("user_service.request_join"):
        # Guard: Validate credentials
        if house_code != settings.house_code or password != settings.house_password:
            msg = "Invalid house code or password"
            logger.warning("Failed join request for %s: %s", phone, msg)
            raise ValueError(msg)

        # Guard: Check if user already exists
        existing_user = await db_client.get_first_record(
            collection="users",
            filter_query=f'phone = "{phone}"',
        )
        if existing_user:
            msg = f"User with phone {phone} already exists"
            logger.warning(msg)
            raise ValueError(msg)

        # Create pending user
        # Generate email from phone for PocketBase auth collection requirement
        email = f"{phone.replace('+', '').replace('-', '')}@choresir.local"
        user_data = {
            "phone": phone,
            "name": name,
            "email": email,
            "role": UserRole.MEMBER,
            "status": UserStatus.PENDING,
            "password": "temp_password_will_be_set_on_activation",
            "passwordConfirm": "temp_password_will_be_set_on_activation",
        }

        record = await db_client.create_record(collection="users", data=user_data)
        logger.info("Created pending user: %s (%s)", name, phone)

        return record


async def approve_member(*, admin_user_id: str, target_phone: str) -> dict[str, Any]:
    """Approve a pending member (admin-only).

    Changes user status from "pending" to "active".

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
        admin_record = await db_client.get_record(collection="users", record_id=admin_user_id)
        if admin_record["role"] != UserRole.ADMIN:
            msg = f"User {admin_user_id} is not authorized to approve members"
            logger.warning(msg)
            raise PermissionError(msg)

        # Guard: Find target user
        target_user = await db_client.get_first_record(
            collection="users",
            filter_query=f'phone = "{target_phone}"',
        )
        if not target_user:
            msg = f"User with phone {target_phone} not found"
            raise KeyError(msg)

        # Guard: Check user is pending
        if target_user["status"] != UserStatus.PENDING:
            msg = f"User {target_phone} is not pending approval (status: {target_user['status']})"
            logger.warning(msg)
            raise ValueError(msg)

        # Approve user
        updated_record = await db_client.update_record(
            collection="users",
            record_id=target_user["id"],
            data={"status": UserStatus.ACTIVE},
        )

        logger.info("Approved user %s by admin %s", target_phone, admin_user_id)

        return updated_record


async def ban_user(*, admin_user_id: str, target_user_id: str) -> dict[str, Any]:
    """Ban a user (admin-only).

    Changes user status to "banned".

    Args:
        admin_user_id: ID of the admin performing the ban
        target_user_id: ID of the user to ban

    Returns:
        Updated user record

    Raises:
        UnauthorizedError: If requesting user is not an admin
        db_client.RecordNotFoundError: If admin or target user not found
    """
    with span("user_service.ban_user"):
        # Guard: Verify admin privileges
        admin_record = await db_client.get_record(collection="users", record_id=admin_user_id)
        if admin_record["role"] != UserRole.ADMIN:
            msg = f"User {admin_user_id} is not authorized to ban users"
            logger.warning(msg)
            raise PermissionError(msg)

        # Guard: Verify target user exists (will raise if not found)
        await db_client.get_record(collection="users", record_id=target_user_id)

        # Ban user
        updated_record = await db_client.update_record(
            collection="users",
            record_id=target_user_id,
            data={"status": UserStatus.BANNED},
        )

        logger.info("Banned user %s by admin %s", target_user_id, admin_user_id)

        return updated_record


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
        collection="users",
        filter_query=f'phone = "{phone}"',
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
    return await db_client.get_record(collection="users", record_id=user_id)
