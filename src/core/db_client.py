"""SQLite client wrapper with CRUD operations.

Replaces the previous PocketBase client with a local SQLite implementation
while maintaining the same interface for the service layer.
"""

import json
import logging
import re
import secrets
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import aiosqlite

from src.core.config import settings


logger = logging.getLogger(__name__)


# Global database connection
_connection: aiosqlite.Connection | None = None


def sanitize_param(value: str | int | float | bool | None) -> str:
    """Sanitize a value for use in filter queries.

    Uses json.dumps to properly escape quotes and backslashes.
    The result is safe to embed in filter strings which are then parsed into parameterized SQL.

    Args:
        value: The value to sanitize

    Returns:
        A properly escaped string value (without surrounding quotes)
    """
    # Emulate the behavior of the previous implementation to ensure compatibility
    # with existing f-strings in services (e.g. f'field = "{sanitize_param(val)}"')
    return json.dumps(str(value))[1:-1]


async def get_db() -> aiosqlite.Connection:
    """Get the global SQLite connection, initializing it if necessary."""
    global _connection
    if _connection is None:
        db_path = Path(settings.sqlite_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Connecting to SQLite database at %s", db_path)
        _connection = await aiosqlite.connect(db_path)
        _connection.row_factory = aiosqlite.Row

        # Enable foreign keys
        await _connection.execute("PRAGMA foreign_keys = ON")

    return _connection


async def close_db() -> None:
    """Close the global SQLite connection."""
    global _connection
    if _connection:
        await _connection.close()
        _connection = None
        logger.info("Closed SQLite connection")


def _parse_filter(filter_query: str) -> tuple[str, list[Any]]:
    """Parse a PocketBase-style filter string into a SQL WHERE clause and parameters.

    Supports:
    - && (AND)
    - = (equality)
    - != (inequality)
    - >=, <=, >, < (comparison)
    - ~ (contains/like)
    """
    if not filter_query:
        return "", []

    # Split by && (AND)
    parts = filter_query.split("&&")
    conditions = []
    params = []

    # Improved regex: longer operators first, tolerant of whitespace
    # Matches: field, operator, value
    pattern = re.compile(r'^\s*([\w\.]+)\s*(!=|>=|<=|=|>|<|~)\s*(.+?)\s*$', re.IGNORECASE)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        match = pattern.match(part)
        if match:
            field, op, value_str = match.groups()

            # Parse value
            value: Any = None
            if value_str.startswith('"') and value_str.endswith('"'):
                # Double quoted string
                try:
                    value = json.loads(value_str)
                except json.JSONDecodeError:
                    value = value_str[1:-1]
            elif value_str.startswith("'") and value_str.endswith("'"):
                # Single quoted string
                value = value_str[1:-1]
            elif value_str.lower() == "true":
                value = 1
            elif value_str.lower() == "false":
                value = 0
            elif value_str.lower() == "null":
                value = None
            else:
                # Number or unquoted string
                try:
                    if '.' in value_str:
                        value = float(value_str)
                    else:
                        value = int(value_str)
                except ValueError:
                    value = value_str

            # Map operators
            if op == "~":
                op = "LIKE"
                value = f"%{value}%"

            conditions.append(f"{field} {op} ?")
            params.append(value)
        else:
            logger.warning("Could not parse filter part: '%s'", part)
            # Log hex representation for debugging hidden chars
            logger.debug("Filter part hex: %s", part.encode().hex())

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    return where_clause, params


def _parse_sort(sort: str) -> str:
    """Parse a PocketBase-style sort string into SQL ORDER BY clause."""
    if not sort:
        return ""

    parts = sort.split(",")
    order_clauses = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part.startswith("-"):
            order_clauses.append(f"{part[1:]} DESC")
        elif part.startswith("+"):
            order_clauses.append(f"{part[1:]} ASC")
        else:
            order_clauses.append(f"{part} ASC")

    return " ORDER BY " + ", ".join(order_clauses)


async def create_record(*, collection: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new record in the specified collection."""
    try:
        db = await get_db()

        # Prepare data
        data = data.copy()
        if "id" not in data:
            data["id"] = secrets.token_hex(8) # 16 chars

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        if "created" not in data:
            data["created"] = now
        if "updated" not in data:
            data["updated"] = now

        # Handle booleans
        for k, v in data.items():
            if isinstance(v, bool):
                data[k] = 1 if v else 0

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        values = list(data.values())

        query = f"INSERT INTO {collection} ({columns}) VALUES ({placeholders}) RETURNING *"

        logger.debug("Executing create: %s", query)

        async with db.execute(query, values) as cursor:
            row = await cursor.fetchone()
            await db.commit()
            if row:
                return dict(row)
            raise RuntimeError("Failed to return created record")

    except Exception as e:
        logger.error(
            "create_record_failed",
            extra={"collection": collection, "error": str(e)},
        )
        msg = f"Failed to create record in {collection}: {e}"
        raise RuntimeError(msg) from e


async def get_record(*, collection: str, record_id: str) -> dict[str, Any]:
    """Get a record by ID from the specified collection."""
    try:
        db = await get_db()
        query = f"SELECT * FROM {collection} WHERE id = ?"

        async with db.execute(query, (record_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                msg = f"Record not found in {collection}: {record_id}"
                raise KeyError(msg)
            return dict(row)

    except KeyError:
        raise
    except Exception as e:
        logger.error(
            "get_record_failed",
            extra={"collection": collection, "record_id": record_id, "error": str(e)},
        )
        msg = f"Failed to get record from {collection}: {e}"
        raise RuntimeError(msg) from e


async def update_record(*, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update a record in the specified collection."""
    try:
        db = await get_db()

        data = data.copy()
        data["updated"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Handle booleans
        for k, v in data.items():
            if isinstance(v, bool):
                data[k] = 1 if v else 0

        set_clauses = [f"{k} = ?" for k in data.keys()]
        values = list(data.values())
        values.append(record_id)

        query = f"UPDATE {collection} SET {', '.join(set_clauses)} WHERE id = ? RETURNING *"

        async with db.execute(query, values) as cursor:
            row = await cursor.fetchone()
            await db.commit()
            if not row:
                msg = f"Record not found in {collection}: {record_id}"
                raise KeyError(msg)
            return dict(row)

    except KeyError:
        raise
    except Exception as e:
        logger.error(
            "update_record_failed",
            extra={"collection": collection, "record_id": record_id, "error": str(e)},
        )
        msg = f"Failed to update record in {collection}: {e}"
        raise RuntimeError(msg) from e


async def delete_record(*, collection: str, record_id: str) -> None:
    """Delete a record from the specified collection."""
    try:
        db = await get_db()
        query = f"DELETE FROM {collection} WHERE id = ?"

        async with db.execute(query, (record_id,)) as cursor:
            if cursor.rowcount == 0:
                msg = f"Record not found in {collection}: {record_id}"
                raise KeyError(msg)
            await db.commit()

    except KeyError:
        raise
    except Exception as e:
        logger.error(
            "delete_record_failed",
            extra={"collection": collection, "record_id": record_id, "error": str(e)},
        )
        msg = f"Failed to delete record from {collection}: {e}"
        raise RuntimeError(msg) from e


async def list_records(
    *,
    collection: str,
    page: int = 1,
    per_page: int = 50,
    filter_query: str = "",
    sort: str = "",
) -> list[dict[str, Any]]:
    """List records from the specified collection with filtering and pagination."""
    try:
        db = await get_db()

        where_clause, params = _parse_filter(filter_query)
        order_clause = _parse_sort(sort)

        limit = per_page
        offset = (page - 1) * per_page

        query = f"SELECT * FROM {collection}{where_clause}{order_clause} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(
            "list_records_failed",
            extra={"collection": collection, "error": str(e)},
        )
        msg = f"Failed to list records from {collection}: {e}"
        raise RuntimeError(msg) from e


async def get_first_record(*, collection: str, filter_query: str) -> dict[str, Any] | None:
    """Get the first record matching the filter query, or None if not found."""
    try:
        db = await get_db()

        where_clause, params = _parse_filter(filter_query)
        query = f"SELECT * FROM {collection}{where_clause} LIMIT 1"

        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    except Exception as e:
        logger.error(
            "get_first_record_failed",
            extra={"collection": collection, "filter_query": filter_query, "error": str(e)},
        )
        msg = f"Failed to get first record from {collection}: {e}"
        raise RuntimeError(msg) from e
