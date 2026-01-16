#!/usr/bin/env python3
"""Inspect the processed_messages collection using httpx directly."""

import asyncio

import httpx
from pocketbase import PocketBase


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
            collection.get(rule)

        if "schema" in collection:
            for field in collection["schema"]:
                if "options" in field:
                    pass
        else:
            pass


if __name__ == "__main__":
    asyncio.run(main())
