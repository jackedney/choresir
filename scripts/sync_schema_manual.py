#!/usr/bin/env python3
"""Manually trigger schema sync."""

import asyncio

from src.core.config import settings
from src.core.schema import sync_schema


async def main() -> None:
    await sync_schema(
        admin_email=settings.require_credential("pocketbase_admin_email", "PocketBase admin email"),
        admin_password=settings.require_credential("pocketbase_admin_password", "PocketBase admin password"),
    )


if __name__ == "__main__":
    asyncio.run(main())
