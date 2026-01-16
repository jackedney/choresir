"""PocketBase schema management (code-first approach)."""

import logging
from typing import Any

import httpx
from pocketbase import PocketBase
from pocketbase.client import ClientResponseError

from src.core.config import settings


logger = logging.getLogger(__name__)


# Central list of all collections in the schema
COLLECTIONS = ["users", "chores", "logs"]


def _get_collection_schema(*, collection_name: str) -> dict[str, Any]:
    """Get the expected schema for a collection."""
    schemas = {
        "users": {
            "name": "users",
            "type": "auth",
            "system": False,
            "schema": [
                {"name": "phone", "type": "text", "required": True, "options": {"pattern": r"^\+[1-9]\d{1,14}$"}},
                {"name": "role", "type": "select", "required": True, "options": {"values": ["admin", "member"]}},
                {
                    "name": "status",
                    "type": "select",
                    "required": True,
                    "options": {"values": ["pending", "active", "banned"]},
                },
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_phone ON users (phone)"],
        },
        "chores": {
            "name": "chores",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "title", "type": "text", "required": True},
                {"name": "description", "type": "text", "required": False},
                {"name": "schedule_cron", "type": "text", "required": True},
                {"name": "assigned_to", "type": "relation", "required": True, "options": {"collectionId": "users"}},
                {
                    "name": "current_state",
                    "type": "select",
                    "required": True,
                    "options": {
                        "values": ["TODO", "PENDING_VERIFICATION", "COMPLETED", "CONFLICT", "DEADLOCK"],
                    },
                },
                {"name": "deadline", "type": "date", "required": True},
            ],
        },
        "logs": {
            "name": "logs",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "chore_id", "type": "relation", "required": True, "options": {"collectionId": "chores"}},
                {"name": "user_id", "type": "relation", "required": True, "options": {"collectionId": "users"}},
                {"name": "action", "type": "text", "required": True},
                {"name": "timestamp", "type": "date", "required": True},
            ],
        },
    }
    return schemas[collection_name]


async def _collection_exists(*, client: httpx.AsyncClient, collection_name: str) -> bool:
    """Check if a collection exists in PocketBase."""
    try:
        response = await client.get(f"/api/collections/{collection_name}")
        return response.is_success
    except httpx.HTTPError:
        return False


async def _create_collection(*, client: httpx.AsyncClient, schema: dict[str, Any]) -> None:
    """Create a new collection in PocketBase."""
    response = await client.post("/api/collections", json=schema)
    response.raise_for_status()
    logger.info("Created collection: %s", schema["name"])


async def sync_schema(
    pocketbase_url: str | None = None,
    admin_email: str = "admin@test.local",
    admin_password: str = "testpassword123",  # noqa: S107
) -> None:
    """Sync PocketBase schema with domain models (idempotent).

    Args:
        pocketbase_url: Optional PocketBase URL. If not provided, uses settings.pocketbase_url.
        admin_email: Admin email for authentication (default for tests).
        admin_password: Admin password for authentication (default for tests).
    """
    logger.info("Starting PocketBase schema sync...")

    url = pocketbase_url or settings.pocketbase_url
    client = PocketBase(url)

    # Authenticate as admin using PocketBase SDK
    try:
        client.admins.auth_with_password(admin_email, admin_password)
        logger.info("Successfully authenticated as admin")
    except ClientResponseError as e:
        logger.error(f"Failed to authenticate as admin: {e}")
        raise

    # Use httpx with the auth token from PocketBase SDK
    async with httpx.AsyncClient(base_url=url, timeout=30.0) as http_client:
        # Set authorization header
        http_client.headers["Authorization"] = f"Bearer {client.auth_store.token}"

        for collection_name in COLLECTIONS:
            schema = _get_collection_schema(collection_name=collection_name)

            if not await _collection_exists(client=http_client, collection_name=collection_name):
                await _create_collection(client=http_client, schema=schema)
            else:
                logger.info("Collection already exists: %s", collection_name)

    logger.info("PocketBase schema sync complete")
