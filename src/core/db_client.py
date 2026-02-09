"""SQLite database client wrapper with CRUD operations."""

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from src.core.config import settings


logger = logging.getLogger(__name__)


def _validate_collection_name(collection: str) -> None:
    """Validate that a collection name is safe for use in SQL queries.

    Collection names must only contain alphanumeric characters and underscores.

    Args:
        collection: Collection/table name to validate

    Raises:
        ValueError: If collection name contains invalid characters
    """
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", collection):
        msg = f"Invalid collection name: {collection}. Only alphanumeric characters and underscores are allowed."
        raise ValueError(msg)


def sanitize_param(value: str | int | float | bool | None) -> str:
    """Sanitize a value for use in SQL queries.

    Uses json.dumps to properly escape quotes and backslashes, preventing
    SQL injection attacks. The result is safe to embed in SQL queries.

    Args:
        value: The value to sanitize (will be converted to string)

    Returns:
        A properly escaped string value (without surrounding quotes)

    Example:
        >>> phone = 'foo" OR 1=1 OR "'
        >>> query = f"phone = '{sanitize_param(phone)}'"
        # Results in: phone = 'foo\" OR 1=1 OR \"'
        # Which safely treats the injection attempt as a literal string
    """
    return json.dumps(str(value))[1:-1]


def get_db_path(db_path: str | None = None) -> Path:
    """Get the SQLite database file path.

    Args:
        db_path: Optional custom database path. If not provided, uses settings.sqlite_db_path.

    Returns:
        Path object pointing to the SQLite database file
    """
    path_str = db_path or settings.sqlite_db_path
    return Path(path_str).resolve()


def _parse_value(value: str, *, is_like: bool = False) -> str | int | float | None:
    """Parse a string value to appropriate type for SQLite.

    Handles LIKE patterns, numeric types, booleans, and None.

    Args:
        value: String value to parse
        is_like: Whether this is for a LIKE pattern (preserve wildcards)

    Returns:
        Parsed value (int, float, str, None, or bool)
    """
    if is_like:
        return value.replace("%", "\\%").replace("_", "\\_")

    if value.isdigit():
        return int(value)
    if value.replace(".", "", 1).isdigit():
        return float(value)

    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    return value


def parse_filter(filter_query: str) -> tuple[str, list[str | int | float | None]]:
    """Parse PocketBase-style filter syntax into SQL WHERE clause and parameters.

    Supports:
    - field = 'value'           -> WHERE field = ?
    - field != 'value'          -> WHERE field != ?
    - field > 'value'           -> WHERE field > ?
    - field < 'value'           -> WHERE field < ?
    - field >= 'value'          -> WHERE field >= ?
    - field <= 'value'          -> WHERE field <= ?
    - field ~ 'pattern'         -> WHERE field LIKE ?
    - field1 = 'v1' && field2 = 'v2' -> WHERE field1 = ? AND field2 = ?

    Args:
        filter_query: PocketBase-style filter string

    Returns:
        Tuple of (WHERE clause, parameter values list)

    Raises:
        ValueError: If filter syntax is invalid
    """
    if not filter_query:
        return "", []

    conditions = []
    params = []

    comparisons = [c.strip() for c in filter_query.split("&&")]

    for comparison in comparisons:
        match = re.match(
            r"(\w+)\s*(=|!=|>|<|>=|<=|~)\s*'([^']*)'",
            comparison,
        )
        if not match:
            msg = f"Invalid filter syntax: {comparison}"
            raise ValueError(msg)

        field = match.group(1)
        op = match.group(2)
        raw_value = match.group(3)

        op_map = {
            "=": "=",
            "!=": "!=",
            ">": ">",
            "<": "<",
            ">=": ">=",
            "<=": "<=",
            "~": "LIKE",
        }

        sql_op = op_map.get(op)
        if not sql_op:
            msg = f"Unsupported operator: {op}"
            raise ValueError(msg)

        is_like = sql_op == "LIKE"
        value = _parse_value(raw_value, is_like=is_like)

        conditions.append(f"{field} {sql_op} ?")
        params.append(value)

    return " AND ".join(conditions), params


_db_connections: dict[int, aiosqlite.Connection] = {}
_db_lock = threading.Lock()


async def get_connection(*, db_path: str | None = None) -> aiosqlite.Connection:
    """Get or create a thread-local SQLite connection.

    Auto-creates the parent directory if it doesn't exist.

    Args:
        db_path: Optional custom database path

    Returns:
        SQLite connection for the current thread

    Raises:
        OSError: If directory creation fails
    """
    thread_id = threading.get_ident()

    if thread_id in _db_connections:
        return _db_connections[thread_id]

    path = get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(str(path))
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA journal_mode = WAL")

    with _db_lock:
        _db_connections[thread_id] = conn

    logger.info("Created new SQLite connection", extra={"db_path": str(path), "thread_id": thread_id})
    return conn


async def close_connection() -> None:
    """Close the current thread's SQLite connection.

    Silently ignores errors if connection is already closed.
    """
    thread_id = threading.get_ident()

    if thread_id not in _db_connections:
        return

    try:
        conn = _db_connections[thread_id]
        await conn.close()
        del _db_connections[thread_id]
        logger.info("Closed SQLite connection", extra={"thread_id": thread_id})
    except Exception as e:
        logger.warning("Error closing SQLite connection", extra={"error": str(e), "thread_id": thread_id})


async def init_db(*, db_path: str | None = None) -> None:
    """Initialize the database schema.

    Delegates to schema.init_db() which creates all required tables.

    Args:
        db_path: Optional custom database path

    Raises:
        RuntimeError: If schema initialization fails
    """
    schema = __import__("src.core.schema", fromlist=["init_db"])
    await schema.init_db(db_path=db_path)


async def create_record(*, collection: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new record in specified collection.

    Args:
        collection: Table/collection name
        data: Record data as dictionary

    Returns:
        Created record with id field

    Raises:
        RuntimeError: If record creation fails or table doesn't exist
    """
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        columns = list(data.keys())
        placeholders = ["?" for _ in columns]
        columns_str = ", ".join(columns)
        placeholders_str = ", ".join(placeholders)

        values = []
        for key in columns:
            val = data[key]
            if isinstance(val, datetime):
                values.append(val.isoformat())
            elif isinstance(val, dict | list):
                values.append(json.dumps(val))
            else:
                values.append(val)

        query = f"INSERT INTO {collection} ({columns_str}) VALUES ({placeholders_str})"  # noqa: S608 - collection is validated
        cursor = await conn.execute(query, values)
        await conn.commit()

        record_id = cursor.lastrowid
        result = await get_record(collection=collection, record_id=str(record_id))

        logger.info("Created record in %s: %s", collection, record_id)
        return result
    except Exception as e:
        if isinstance(e, aiosqlite.OperationalError) and "no such table" in str(e):
            msg = f"Table '{collection}' does not exist. Call init_db() first."
            logger.error("Table not found", extra={"collection": collection})
            raise RuntimeError(msg) from e
        logger.error("create_record_failed", extra={"collection": collection, "error": str(e)})
        msg = f"Failed to create record in {collection}: {e}"
        raise RuntimeError(msg) from e


async def get_record(*, collection: str, record_id: str) -> dict[str, Any]:
    """Get a record by ID from specified collection.

    Args:
        collection: Table/collection name
        record_id: Record ID (as string)

    Returns:
        Record as dictionary

    Raises:
        KeyError: If record not found
        RuntimeError: If query fails
    """
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        query = f"SELECT * FROM {collection} WHERE id = ?"  # noqa: S608 - collection is validated
        cursor = await conn.execute(query, (int(record_id),))
        row = await cursor.fetchone()

        if row is None:
            msg = f"Record not found in {collection}: {record_id}"
            raise KeyError(msg)

        columns = [description[0] for description in cursor.description]
        record = dict(zip(columns, row, strict=True))

        logger.info("Retrieved record from %s: %s", collection, record_id)
        return record
    except KeyError:
        raise
    except Exception as e:
        logger.error("get_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        msg = f"Failed to get record from {collection}: {e}"
        raise RuntimeError(msg) from e


async def update_record(*, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update a record in specified collection.

    Args:
        collection: Table/collection name
        record_id: Record ID (as string)
        data: Updated record data

    Returns:
        Updated record as dictionary

    Raises:
        KeyError: If record not found
        RuntimeError: If update fails
    """
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        set_clause = ", ".join(f"{key} = ?" for key in data)
        values = []

        for val in data.values():
            if isinstance(val, datetime):
                values.append(val.isoformat())
            elif isinstance(val, dict | list):
                values.append(json.dumps(val))
            else:
                values.append(val)

        values.append(int(record_id))

        query = f"UPDATE {collection} SET {set_clause} WHERE id = ?"  # noqa: S608 - collection is validated
        await conn.execute(query, values)
        await conn.commit()

        logger.info("Updated record in %s: %s", collection, record_id)
        return await get_record(collection=collection, record_id=record_id)
    except KeyError:
        raise
    except Exception as e:
        logger.error("update_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        msg = f"Failed to update record in {collection}: {e}"
        raise RuntimeError(msg) from e


async def delete_record(*, collection: str, record_id: str) -> None:
    """Delete a record from specified collection.

    Args:
        collection: Table/collection name
        record_id: Record ID (as string)

    Raises:
        KeyError: If record not found
        RuntimeError: If deletion fails
    """
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        query = f"DELETE FROM {collection} WHERE id = ?"  # noqa: S608 - collection is validated
        cursor = await conn.execute(query, (int(record_id),))
        await conn.commit()

        if cursor.rowcount == 0:
            msg = f"Record not found in {collection}: {record_id}"
            raise KeyError(msg)

        logger.info("Deleted record from %s: %s", collection, record_id)
    except KeyError:
        raise
    except Exception as e:
        logger.error("delete_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
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
    """List records from specified collection with filtering and pagination.

    Args:
        collection: Table/collection name
        page: Page number (1-indexed)
        per_page: Records per page
        filter_query: PocketBase-style filter string
        sort: Sort field (default: id ASC)

    Returns:
        List of records as dictionaries

    Raises:
        RuntimeError: If query fails
    """
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        where_clause = ""
        params = []
        if filter_query:
            where_clause, params = parse_filter(filter_query)
            where_clause = f"WHERE {where_clause}"

        sort = sanitize_param(sort) if sort else "id ASC"

        offset = (page - 1) * per_page

        query = f"SELECT * FROM {collection} {where_clause} ORDER BY {sort} LIMIT ? OFFSET ?"  # noqa: S608 - collection is validated
        params.extend([per_page, offset])

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()

        columns = [description[0] for description in cursor.description]
        records = [dict(zip(columns, row, strict=True)) for row in rows]

        logger.info("Listed records from %s: %d results", collection, len(records))
        return records
    except Exception as e:
        logger.error("list_records_failed", extra={"collection": collection, "error": str(e)})
        msg = f"Failed to list records from {collection}: {e}"
        raise RuntimeError(msg) from e


async def get_first_record(*, collection: str, filter_query: str) -> dict[str, Any] | None:
    """Get first record matching filter query, or None if not found.

    Args:
        collection: Table/collection name
        filter_query: PocketBase-style filter string

    Returns:
        First matching record as dictionary, or None if not found

    Raises:
        RuntimeError: If query fails
    """
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        where_clause, params = parse_filter(filter_query)
        query = f"SELECT * FROM {collection} WHERE {where_clause} LIMIT 1"  # noqa: S608 - collection is validated

        cursor = await conn.execute(query, params)
        row = await cursor.fetchone()

        if row is None:
            return None

        columns = [description[0] for description in cursor.description]
        record = dict(zip(columns, row, strict=True))

        logger.info("Retrieved first record from %s", collection)
        return record
    except Exception as e:
        logger.error(
            "get_first_record_failed", extra={"collection": collection, "filter_query": filter_query, "error": str(e)}
        )
        msg = f"Failed to get first record from {collection}: {e}"
        raise RuntimeError(msg) from e
