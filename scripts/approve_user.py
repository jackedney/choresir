#!/usr/bin/env python3
"""Admin script to approve pending users.

Usage:
    uv run python scripts/approve_user.py <phone_number> [--role admin|member]
    uv run python scripts/approve_user.py --list-pending
"""

import asyncio
import sys

from src.core import db_client
from src.domain.user import UserStatus


async def list_pending_users() -> None:
    """List all pending users."""
    pending_users = await db_client.list_records(
        collection="users",
        filter_query=f'status = "{UserStatus.PENDING}"',
    )

    if not pending_users:
        return

    for _user in pending_users:
        pass


async def approve_user(phone: str, role: str = "member") -> None:
    """Approve a pending user and set their role.

    Args:
        phone: Phone number of the user to approve
        role: Role to assign (admin or member)
    """
    # Find user by phone
    user = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{phone}"',
    )

    if not user:
        sys.exit(1)
        return  # Type narrowing: ensure user is not None below this point

    current_status = user["status"]
    current_role = user["role"]

    if current_status == UserStatus.ACTIVE:
        if current_role != role:
            pass
        else:
            return

    # Update user
    await db_client.update_record(
        collection="users",
        record_id=user["id"],
        data={
            "status": UserStatus.ACTIVE,
            "role": role,
        },
    )


def print_usage() -> None:
    """Print usage information."""


async def main() -> None:
    """Main entry point."""
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_usage()
        return

    if "--list-pending" in args:
        await list_pending_users()
        return

    # Parse phone and role
    phone = args[0]
    role = "member"  # default

    if "--role" in args:
        role_index = args.index("--role")
        if role_index + 1 < len(args):
            role = args[role_index + 1]
            if role not in ["admin", "member"]:
                sys.exit(1)
        else:
            sys.exit(1)

    await approve_user(phone, role)


if __name__ == "__main__":
    asyncio.run(main())
