#!/usr/bin/env python3
"""Manually trigger schema sync."""

import asyncio

from src.core.config import settings
from src.core.schema import sync_schema


async def main() -> None:
    await sync_schema(
        admin_email=settings.pocketbase_admin_email,
        admin_password=settings.pocketbase_admin_password,
    )


if __name__ == "__main__":
    asyncio.run(main())
