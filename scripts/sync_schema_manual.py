#!/usr/bin/env python3
"""Manually trigger schema sync."""

import asyncio

from src.core.config import settings
from src.core.schema import sync_schema


async def main() -> None:
    # Ensure credentials are present
    admin_email = settings.require_credential("pocketbase_admin_email", "PocketBase Admin Email")
    admin_password = settings.require_credential("pocketbase_admin_password", "PocketBase Admin Password")

    await sync_schema(
        admin_email=admin_email,
        admin_password=admin_password,
    )


if __name__ == "__main__":
    asyncio.run(main())
