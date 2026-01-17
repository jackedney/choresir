#!/usr/bin/env python3
"""Manually trigger schema sync."""

import asyncio

from src.core.schema import sync_schema


async def main() -> None:
    await sync_schema()


if __name__ == "__main__":
    asyncio.run(main())
