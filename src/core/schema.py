"""PocketBase schema management (code-first approach)."""

import logging
from typing import Any

import httpx

from src.core.config import settings


logger = logging.getLogger(__name__)


def _get_collection_schema(*, collection_name: str) -> dict[str, Any]:
    """Get the expected schema for a collection."""
    schemas = {
        "users": {
            "name": "users",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "phone", "type": "text", "required": True, "options": {"pattern": r"^\+[1-9]\d{1,14}$"}},
                {"name": "name", "type": "text", "required": True},
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
        "processed_messages": {
            "name": "processed_messages",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "message_id", "type": "text", "required": True},
                {"name": "from_phone", "type": "text", "required": True},
                {"name": "processed_at", "type": "date", "required": True},
                {"name": "success", "type": "bool", "required": True},
                {"name": "error_message", "type": "text", "required": False},
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_message_id ON processed_messages (message_id)"],
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


async def sync_schema() -> None:
    """Sync PocketBase schema with domain models (idempotent)."""
    logger.info("Starting PocketBase schema sync...")

    async with httpx.AsyncClient(base_url=settings.pocketbase_url, timeout=30.0) as client:
        for collection_name in ["users", "chores", "logs", "processed_messages"]:
            schema = _get_collection_schema(collection_name=collection_name)

            if not await _collection_exists(client=client, collection_name=collection_name):
                await _create_collection(client=client, schema=schema)
            else:
                logger.info("Collection already exists: %s", collection_name)

    logger.info("PocketBase schema sync complete")
