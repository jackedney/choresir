"""PocketBase schema management (code-first approach)."""

import logging
from typing import Any

import httpx

from src.core.config import settings


logger = logging.getLogger(__name__)


# Central list of all collections in the schema
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


def _get_collection_schema(
    *,
    collection_name: str,
    collection_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Get the expected schema for a collection.

    Note: PocketBase v0.22+ uses 'fields' instead of 'schema' for field definitions,
    and field options are flattened directly onto the field object (not nested in 'options').
    PocketBase requires actual collection IDs (not names) in relation fields.

    Args:
        collection_name: The name of the collection to get the schema for.
        collection_ids: Optional mapping of collection names to their actual IDs.
            When provided, relation fields will use the actual IDs instead of names.
    """
    ids = collection_ids or {}

    schemas = {
        "users": {
            "name": "users",
            "type": "auth",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "phone", "type": "text", "required": True, "pattern": r"^\+[1-9]\d{1,14}$"},
                {"name": "role", "type": "select", "required": True, "values": ["admin", "member"], "maxSelect": 1},
                {
                    "name": "status",
                    "type": "select",
                    "required": True,
                    "values": ["pending", "active"],
                    "maxSelect": 1,
                },
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_phone ON users (phone)"],
        },
        "chores": {
            "name": "chores",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "title", "type": "text", "required": True},
                {"name": "description", "type": "text", "required": False},
                {"name": "schedule_cron", "type": "text", "required": True},
                {
                    "name": "assigned_to",
                    "type": "relation",
                    "required": True,
                    "collectionId": ids.get("users", "users"),
                    "maxSelect": 1,
                },
                {
                    "name": "current_state",
                    "type": "select",
                    "required": True,
                    "values": ["TODO", "PENDING_VERIFICATION", "COMPLETED", "CONFLICT", "DEADLOCK"],
                    "maxSelect": 1,
                },
                {"name": "deadline", "type": "date", "required": True},
            ],
        },
        "logs": {
            "name": "logs",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {
                    "name": "chore_id",
                    "type": "relation",
                    "required": False,
                    "collectionId": ids.get("chores", "chores"),
                    "maxSelect": 1,
                },
                {
                    "name": "user_id",
                    "type": "relation",
                    "required": False,
                    "collectionId": ids.get("users", "users"),
                    "maxSelect": 1,
                },
                {"name": "action", "type": "text", "required": False},
                {"name": "notes", "type": "text", "required": False},
                {"name": "timestamp", "type": "date", "required": False},
                {
                    "name": "original_assignee_id",
                    "type": "relation",
                    "required": False,
                    "collectionId": ids.get("users", "users"),
                    "maxSelect": 1,
                },
                {
                    "name": "actual_completer_id",
                    "type": "relation",
                    "required": False,
                    "collectionId": ids.get("users", "users"),
                    "maxSelect": 1,
                },
                {"name": "is_swap", "type": "bool", "required": False},
            ],
        },
        "robin_hood_swaps": {
            "name": "robin_hood_swaps",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {
                    "name": "user_id",
                    "type": "relation",
                    "required": True,
                    "collectionId": ids.get("users", "users"),
                    "maxSelect": 1,
                },
                {"name": "week_start_date", "type": "date", "required": True},
                {"name": "takeover_count", "type": "number", "required": True},
            ],
            "indexes": [
                "CREATE UNIQUE INDEX idx_user_week ON robin_hood_swaps (user_id, week_start_date)",
            ],
        },
        "processed_messages": {
            "name": "processed_messages",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "message_id", "type": "text", "required": True},
                {"name": "from_phone", "type": "text", "required": True},
                {"name": "processed_at", "type": "date", "required": True},
                # Note: required=False due to PocketBase bug where False values fail validation on required bool fields
                {"name": "success", "type": "bool", "required": False},
                {"name": "error_message", "type": "text", "required": False},
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_message_id ON processed_messages (message_id)"],
        },
        "pantry_items": {
            "name": "pantry_items",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "name", "type": "text", "required": True},
                {"name": "quantity", "type": "number", "required": False},
                {
                    "name": "status",
                    "type": "select",
                    "required": True,
                    "values": ["IN_STOCK", "LOW", "OUT"],
                    "maxSelect": 1,
                },
                {"name": "last_restocked", "type": "date", "required": False},
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_pantry_item_name ON pantry_items (name)"],
        },
        "shopping_list": {
            "name": "shopping_list",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "item_name", "type": "text", "required": True},
                {
                    "name": "added_by",
                    "type": "relation",
                    "required": True,
                    "collectionId": ids.get("users", "users"),
                    "maxSelect": 1,
                },
                {"name": "added_at", "type": "date", "required": True},
                {"name": "quantity", "type": "number", "required": False},
                {"name": "notes", "type": "text", "required": False},
            ],
        },
        "personal_chores": {
            "name": "personal_chores",
            "type": "base",
            "system": False,
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "owner_phone", "type": "text", "required": True, "pattern": r"^\+[1-9]\d{1,14}$"},
                {"name": "title", "type": "text", "required": True},
                {"name": "recurrence", "type": "text", "required": False},  # CRON or INTERVAL format
                {"name": "due_date", "type": "date", "required": False},  # For one-time tasks
                {
                    "name": "accountability_partner_phone",
                    "type": "text",
                    "required": False,
                    "pattern": r"^\+[1-9]\d{1,14}$",
                },
                {
                    "name": "status",
                    "type": "select",
                    "required": True,
                    "values": ["ACTIVE", "ARCHIVED"],
                    "maxSelect": 1,
                },
                {"name": "created_at", "type": "date", "required": True},
            ],
            "indexes": [
                "CREATE INDEX idx_personal_owner ON personal_chores (owner_phone)",
                "CREATE INDEX idx_personal_status ON personal_chores (status)",
            ],
        },
        "personal_chore_logs": {
            "name": "personal_chore_logs",
            "type": "base",
            "system": False,
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {
                    "name": "personal_chore_id",
                    "type": "relation",
                    "required": True,
                    "collectionId": ids.get("personal_chores", "personal_chores"),
                    "maxSelect": 1,
                },
                {"name": "owner_phone", "type": "text", "required": True, "pattern": r"^\+[1-9]\d{1,14}$"},
                {"name": "completed_at", "type": "date", "required": True},
                {
                    "name": "verification_status",
                    "type": "select",
                    "required": True,
                    "values": ["SELF_VERIFIED", "PENDING", "VERIFIED", "REJECTED"],
                    "maxSelect": 1,
                },
                {
                    "name": "accountability_partner_phone",
                    "type": "text",
                    "required": False,
                    "pattern": r"^\+[1-9]\d{1,14}$",
                },
                {"name": "partner_feedback", "type": "text", "required": False},
                {"name": "notes", "type": "text", "required": False},
            ],
            "indexes": [
                "CREATE INDEX idx_pcl_chore ON personal_chore_logs (personal_chore_id)",
                "CREATE INDEX idx_pcl_owner ON personal_chore_logs (owner_phone)",
                "CREATE INDEX idx_pcl_verification ON personal_chore_logs (verification_status)",
            ],
        },
        "house_config": {
            "name": "house_config",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "name", "type": "text", "required": True},
                {"name": "password", "type": "text", "required": True},
                {"name": "code", "type": "text", "required": True},
                {"name": "group_chat_id", "type": "text", "required": False},
            ],
        },
        "pending_invites": {
            "name": "pending_invites",
            "type": "base",
            "system": False,
            # API Rules: Admin only (backend uses admin client)
            "listRule": None,
            "viewRule": None,
            "createRule": None,
            "updateRule": None,
            "deleteRule": None,
            "fields": [
                {"name": "phone", "type": "text", "required": True, "pattern": r"^\+[1-9]\d{1,14}$"},
                {"name": "invited_at", "type": "date", "required": True},
                {"name": "invite_message_id", "type": "text", "required": False},
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_pending_invite_phone ON pending_invites (phone)"],
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


async def _get_collection_id(*, client: httpx.AsyncClient, collection_name: str) -> str:
    """Fetch the actual collection ID from PocketBase.

    PocketBase v0.22+ requires actual collection IDs (not names) in relation field options.

    Args:
        client: The httpx client with authorization headers.
        collection_name: The name of the collection.

    Returns:
        The actual collection ID (e.g., "pbc_1234567890").
    """
    response = await client.get(f"/api/collections/{collection_name}")
    response.raise_for_status()
    return response.json()["id"]


async def _create_collection(*, client: httpx.AsyncClient, schema: dict[str, Any]) -> None:
    """Create a new collection in PocketBase."""
    response = await client.post("/api/collections", json=schema)
    response.raise_for_status()
    logger.info("Created collection: %s", schema["name"])


# API rule keys that can be set on collections
_API_RULE_KEYS = ("listRule", "viewRule", "createRule", "updateRule", "deleteRule")


def _merge_fields(
    schema: dict[str, Any],
    current: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Merge desired fields with existing fields.

    Returns:
        Tuple of (merged_fields, fields_updated, fields_added).
    """
    desired_fields = {f["name"]: f for f in schema.get("fields", [])}
    existing_fields = {f["name"]: f for f in current.get("fields", [])}

    merged_fields = []
    fields_updated = []
    fields_added = []

    # Update existing fields or keep them as-is
    for field_name, existing_field in existing_fields.items():
        if field_name in desired_fields:
            merged_fields.append(desired_fields[field_name])
            fields_updated.append(field_name)
        else:
            merged_fields.append(existing_field)

    # Add new fields that don't exist yet
    for field_name, desired_field in desired_fields.items():
        if field_name not in existing_fields:
            merged_fields.append(desired_field)
            fields_added.append(field_name)

    return merged_fields, fields_updated, fields_added


def _get_rules_to_update(
    schema: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, str | None]:
    """Get API rules that need updating.

    Returns:
        Dict of rule keys to their new values.
    """
    rules_to_update: dict[str, str | None] = {}
    for rule_key in _API_RULE_KEYS:
        if rule_key in schema and schema[rule_key] != current.get(rule_key):
            rules_to_update[rule_key] = schema[rule_key]
    return rules_to_update


def _build_update_payload(
    merged_fields: list[dict[str, Any]],
    rules_to_update: dict[str, str | None],
    schema: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Build the update payload for a collection update."""
    update_payload: dict[str, Any] = {"fields": merged_fields}
    update_payload.update(rules_to_update)

    # Include indexes if specified, merging with existing
    if "indexes" in schema:
        existing_indexes = set(current.get("indexes", []))
        new_indexes = [idx for idx in schema["indexes"] if idx not in existing_indexes]
        if new_indexes:
            update_payload["indexes"] = list(existing_indexes) + new_indexes

    return update_payload


async def _update_collection(
    *,
    client: httpx.AsyncClient,
    collection_name: str,
    schema: dict[str, Any],
) -> None:
    """Update an existing collection in PocketBase to add missing fields and update existing ones.

    This merges custom fields with existing fields instead of replacing them,
    which preserves built-in auth collection fields. It also updates properties
    of existing fields to match the desired schema.
    """
    response = await client.get(f"/api/collections/{collection_name}")
    response.raise_for_status()
    current = response.json()

    merged_fields, fields_updated, fields_added = _merge_fields(schema, current)
    rules_to_update = _get_rules_to_update(schema, current)

    if not fields_added and not fields_updated and not rules_to_update:
        logger.info("Collection %s schema is already up to date", collection_name)
        return

    update_payload = _build_update_payload(merged_fields, rules_to_update, schema, current)

    response = await client.patch(f"/api/collections/{collection_name}", json=update_payload)
    response.raise_for_status()

    log_parts = []
    if fields_added:
        log_parts.append(f"added {fields_added}")
    if fields_updated:
        log_parts.append(f"updated {fields_updated}")
    if rules_to_update:
        log_parts.append(f"updated rules {list(rules_to_update.keys())}")
    logger.info("Updated collection %s: %s", collection_name, ", ".join(log_parts))


async def sync_schema(
    *,
    admin_email: str,
    admin_password: str,
    pocketbase_url: str | None = None,
) -> None:
    """Sync PocketBase schema with domain models (idempotent).

    Args:
        admin_email: Admin email for authentication.
        admin_password: Admin password for authentication.
        pocketbase_url: Optional PocketBase URL. If not provided, uses settings.pocketbase_url.

    Raises:
        ValueError: If admin_email or admin_password is empty.
    """
    if not admin_email or not admin_password:
        raise ValueError(
            "sync_schema requires admin_email and admin_password to be provided. "
            "These credentials are required for PocketBase admin authentication."
        )

    logger.info("Starting PocketBase schema sync...")

    url = pocketbase_url or settings.pocketbase_url

    # Use httpx for all operations including authentication
    async with httpx.AsyncClient(base_url=url, timeout=30.0) as http_client:
        # Authenticate as admin using PocketBase API directly
        # PocketBase v0.22+ uses _superusers collection for admin auth
        try:
            auth_response = await http_client.post(
                "/api/collections/_superusers/auth-with-password",
                json={"identity": admin_email, "password": admin_password},
            )
            auth_response.raise_for_status()
            auth_data = auth_response.json()
            http_client.headers["Authorization"] = f"Bearer {auth_data['token']}"
            logger.info("Successfully authenticated as admin")
        except httpx.HTTPStatusError as e:
            logger.error("Failed to authenticate as admin: %s", e)
            raise
        except httpx.RequestError as e:
            logger.error("Connection error during admin authentication: %s", e)
            raise

        # Build collection ID mapping as we create collections.
        # PocketBase requires actual collection IDs (not names) in relation field options.
        collection_ids: dict[str, str] = {}

        for collection_name in COLLECTIONS:
            schema = _get_collection_schema(
                collection_name=collection_name,
                collection_ids=collection_ids,
            )

            if not await _collection_exists(client=http_client, collection_name=collection_name):
                await _create_collection(client=http_client, schema=schema)
            else:
                # Update existing collection to add any missing fields
                await _update_collection(
                    client=http_client,
                    collection_name=collection_name,
                    schema=schema,
                )

            # Fetch and store the collection ID for use by dependent collections
            collection_ids[collection_name] = await _get_collection_id(
                client=http_client,
                collection_name=collection_name,
            )

    logger.info("PocketBase schema sync complete")
