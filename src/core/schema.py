"""SQLite schema management."""

import logging
from typing import Any

from src.core.db_client import get_db


logger = logging.getLogger(__name__)


# Central list of all collections (tables) in the schema
COLLECTIONS = [
    "users",
    "chores",
    "logs",
    "robin_hood_swaps",
    "processed_messages",
    "pantry_items",
    "shopping_list",
    "personal_chores",
    "personal_chore_logs",
    "house_config",
    "pending_invites",
]


def _get_collection_schema(collection_name: str) -> dict[str, Any]:
    """Get the expected schema for a collection.

    Args:
        collection_name: The name of the collection to get the schema for.
    """
    schemas = {
        "users": {
            "name": "users",
            "fields": [
                {"name": "phone", "type": "text", "required": True},
                {"name": "role", "type": "select", "required": True},
                {"name": "status", "type": "select", "required": True},
                # Implicit fields in PB auth collection, needed explicitly here
                {"name": "name", "type": "text", "required": False},
                {"name": "email", "type": "email", "required": False},
                {"name": "password", "type": "text", "required": False}, # PB auth stores password hash
                {"name": "passwordConfirm", "type": "text", "required": False}, # Not stored typically, but checking
            ],
            "indexes": ["CREATE UNIQUE INDEX IF NOT EXISTS idx_phone ON users (phone)"],
        },
        "chores": {
            "name": "chores",
            "fields": [
                {"name": "title", "type": "text", "required": True},
                {"name": "description", "type": "text", "required": False},
                {"name": "schedule_cron", "type": "text", "required": True},
                {"name": "assigned_to", "type": "relation", "required": True},
                {"name": "current_state", "type": "select", "required": True},
                {"name": "deadline", "type": "date", "required": True},
            ],
        },
        "logs": {
            "name": "logs",
            "fields": [
                {"name": "chore_id", "type": "relation", "required": False},
                {"name": "user_id", "type": "relation", "required": False},
                {"name": "action", "type": "text", "required": False},
                {"name": "notes", "type": "text", "required": False},
                {"name": "timestamp", "type": "date", "required": False},
                {"name": "original_assignee_id", "type": "relation", "required": False},
                {"name": "actual_completer_id", "type": "relation", "required": False},
                {"name": "is_swap", "type": "bool", "required": False},
            ],
        },
        "robin_hood_swaps": {
            "name": "robin_hood_swaps",
            "fields": [
                {"name": "user_id", "type": "relation", "required": True},
                {"name": "week_start_date", "type": "date", "required": True},
                {"name": "takeover_count", "type": "number", "required": True},
            ],
            "indexes": [
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_week ON robin_hood_swaps (user_id, week_start_date)",
            ],
        },
        "processed_messages": {
            "name": "processed_messages",
            "fields": [
                {"name": "message_id", "type": "text", "required": True},
                {"name": "from_phone", "type": "text", "required": True},
                {"name": "processed_at", "type": "date", "required": True},
                {"name": "success", "type": "bool", "required": False},
                {"name": "error_message", "type": "text", "required": False},
            ],
            "indexes": ["CREATE UNIQUE INDEX IF NOT EXISTS idx_message_id ON processed_messages (message_id)"],
        },
        "pantry_items": {
            "name": "pantry_items",
            "fields": [
                {"name": "name", "type": "text", "required": True},
                {"name": "quantity", "type": "number", "required": False},
                {"name": "status", "type": "select", "required": True},
                {"name": "last_restocked", "type": "date", "required": False},
            ],
            "indexes": ["CREATE UNIQUE INDEX IF NOT EXISTS idx_pantry_item_name ON pantry_items (name)"],
        },
        "shopping_list": {
            "name": "shopping_list",
            "fields": [
                {"name": "item_name", "type": "text", "required": True},
                {"name": "added_by", "type": "relation", "required": True},
                {"name": "added_at", "type": "date", "required": True},
                {"name": "quantity", "type": "number", "required": False},
                {"name": "notes", "type": "text", "required": False},
            ],
        },
        "personal_chores": {
            "name": "personal_chores",
            "fields": [
                {"name": "owner_phone", "type": "text", "required": True},
                {"name": "title", "type": "text", "required": True},
                {"name": "recurrence", "type": "text", "required": False},
                {"name": "due_date", "type": "date", "required": False},
                {"name": "accountability_partner_phone", "type": "text", "required": False},
                {"name": "status", "type": "select", "required": True},
                {"name": "created_at", "type": "date", "required": True},
            ],
            "indexes": [
                "CREATE INDEX IF NOT EXISTS idx_personal_owner ON personal_chores (owner_phone)",
                "CREATE INDEX IF NOT EXISTS idx_personal_status ON personal_chores (status)",
            ],
        },
        "personal_chore_logs": {
            "name": "personal_chore_logs",
            "fields": [
                {"name": "personal_chore_id", "type": "relation", "required": True},
                {"name": "owner_phone", "type": "text", "required": True},
                {"name": "completed_at", "type": "date", "required": True},
                {"name": "verification_status", "type": "select", "required": True},
                {"name": "accountability_partner_phone", "type": "text", "required": False},
                {"name": "partner_feedback", "type": "text", "required": False},
                {"name": "notes", "type": "text", "required": False},
            ],
            "indexes": [
                "CREATE INDEX IF NOT EXISTS idx_pcl_chore ON personal_chore_logs (personal_chore_id)",
                "CREATE INDEX IF NOT EXISTS idx_pcl_owner ON personal_chore_logs (owner_phone)",
                "CREATE INDEX IF NOT EXISTS idx_pcl_verification ON personal_chore_logs (verification_status)",
            ],
        },
        "house_config": {
            "name": "house_config",
            "fields": [
                {"name": "name", "type": "text", "required": True},
                {"name": "password", "type": "text", "required": True},
                {"name": "code", "type": "text", "required": True},
            ],
        },
        "pending_invites": {
            "name": "pending_invites",
            "fields": [
                {"name": "phone", "type": "text", "required": True},
                {"name": "invited_at", "type": "date", "required": True},
                {"name": "invite_message_id", "type": "text", "required": False},
            ],
            "indexes": ["CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_invite_phone ON pending_invites (phone)"],
        },
    }
    return schemas[collection_name]


async def init_db() -> None:
    """Initialize the SQLite database schema (idempotent)."""
    logger.info("Initializing SQLite schema...")
    db = await get_db()

    for collection in COLLECTIONS:
        schema = _get_collection_schema(collection)

        # Build CREATE TABLE statement
        columns = [
            "id TEXT PRIMARY KEY",
            "created TEXT NOT NULL",
            "updated TEXT NOT NULL"
        ]

        for field in schema["fields"]:
            name = field["name"]
            type_ = field["type"]

            # Map types to SQLite
            sql_type = "TEXT"
            if type_ == "number":
                sql_type = "REAL"
            elif type_ == "bool":
                sql_type = "INTEGER"

            columns.append(f"{name} {sql_type}")

        create_sql = f"CREATE TABLE IF NOT EXISTS {collection} ({', '.join(columns)})"
        await db.execute(create_sql)

        # Create indexes
        if "indexes" in schema:
            for index_sql in schema["indexes"]:
                try:
                    await db.execute(index_sql)
                except Exception as e:
                    logger.warning("Failed to create index for %s: %s", collection, e)

    await db.commit()
    logger.info("SQLite schema initialization complete")
