#!/usr/bin/env python3
"""Inspect the processed_messages collection using httpx directly."""

import asyncio
import logging

import httpx
from pocketbase import PocketBase


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    # Auth using SDK
    pb = PocketBase("http://127.0.0.1:8090")
    pb.admins.auth_with_password("admin@test.local", "testpassword123")
    token = pb.auth_store.token

    # Get collection info via HTTP
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://127.0.0.1:8090/api/collections/processed_messages", headers={"Authorization": f"Bearer {token}"}
        )

        collection = response.json()

        for rule in ["listRule", "viewRule", "createRule", "updateRule", "deleteRule"]:
            logger.info(f"{rule}: {collection.get(rule)}")

        if "schema" in collection:
            logger.info("Schema fields:")
            for field in collection["schema"]:
                logger.info(f"  - {field.get('name', 'unknown')}: {field.get('type', 'unknown')}")
                if "options" in field:
                    logger.info(f"    options: {field['options']}")
        else:
            logger.info("No schema found")


if __name__ == "__main__":
    asyncio.run(main())
