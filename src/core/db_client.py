"""SQLite database client wrapper with CRUD operations."""

import asyncio
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
    """Validate that a collection name contains only alphanumeric characters and underscores."""
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", collection):
        msg = f"Invalid collection name: {collection}. Only alphanumeric characters and underscores are allowed."
        raise ValueError(msg)


def sanitize_param(value: str | int | float | bool | None) -> str:
    """Escape a value for safe embedding in SQL queries via json.dumps."""
    return json.dumps(str(value))[1:-1]


def _convert_record_ids(record: dict[str, Any]) -> dict[str, Any]:
    """Convert integer ID and foreign key fields to strings for Pydantic compatibility."""
    # Common foreign key field names that should be converted
    fk_fields = {
        "id",
        "assigned_to",
        "claimer_user_id",
        "verifier_user_id",
        "requester_user_id",
        "target_id",
        "personal_chore_id",
    }

    converted = record.copy()
    for key, value in converted.items():
        # Convert if it's a known FK field, ends in _id, or is the primary id
        if isinstance(value, int) and (key in fk_fields or key.endswith("_id")):
            converted[key] = str(value)
    return converted


def get_db_path(db_path: str | None = None) -> Path:
    """Get the resolved SQLite database file path."""
    path_str = db_path or settings.sqlite_db_path
    return Path(path_str).resolve()


def _parse_value(value: str, *, is_like: bool = False) -> str | int | float | bool | None:
    """Parse a string value to the appropriate Python type for SQLite."""
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


def _get_sql_operator(op: str) -> str:
    """Map filter operator to SQL operator."""
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
    return sql_op


def _parse_single_comparison(comparison: str) -> tuple[str, str | int | float | None]:
    """Parse a single comparison expression into a SQL condition and parameter."""
    match = re.match(
        r"""(\w+)\s*(=|!=|>|<|>=|<=|~)\s*(['"])([^'"]*)\3""",
        comparison,
    )
    if not match:
        msg = f"Invalid filter syntax: {comparison}"
        raise ValueError(msg)

    field = match.group(1)
    op = match.group(2)
    raw_value = match.group(4)

    sql_op = _get_sql_operator(op)
    is_like = sql_op == "LIKE"
    value = _parse_value(raw_value, is_like=is_like)

    return f"{field} {sql_op} ?", value


def _parse_or_group(or_group: str) -> tuple[str, list[str | int | float | None]]:
    """Parse a parenthesized OR group into a SQL condition and parameters."""
    inner = or_group[1:-1]  # Remove parentheses
    or_parts = [p.strip() for p in inner.split("||")]
    or_conditions = []
    or_params = []

    for part in or_parts:
        cond, value = _parse_single_comparison(part)
        or_conditions.append(cond)
        or_params.append(value)

    return f"({' OR '.join(or_conditions)})", or_params


def _split_and_conditions(filter_query: str) -> list[str]:
    """Split filter query by && while preserving parenthesized groups."""
    parts = []
    current = ""
    paren_depth = 0

    for char in filter_query:
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1

        current += char

        if paren_depth == 0 and current.endswith("&&"):
            parts.append(current[:-2].strip())
            current = ""

    if current.strip():
        parts.append(current.strip())

    return parts


def parse_filter(filter_query: str) -> tuple[str, list[str | int | float | None]]:
    """Parse filter syntax into a SQL WHERE clause and parameter list."""
    if not filter_query:
        return "", []

    parts = _split_and_conditions(filter_query)
    conditions = []
    params = []

    for raw_part in parts:
        part = raw_part.strip()

        # Handle parenthesized OR groups
        if part.startswith("(") and part.endswith(")"):
            cond, cond_params = _parse_or_group(part)
            conditions.append(cond)
            params.extend(cond_params)
        else:
            # Handle regular condition
            cond, value = _parse_single_comparison(part)
            conditions.append(cond)
            params.append(value)

    return " AND ".join(conditions), params


_db_connections: dict[tuple[int, int, str], aiosqlite.Connection] = {}
_db_lock = asyncio.Lock()


async def get_connection(*, db_path: str | None = None) -> aiosqlite.Connection:
    """Get or create a cached connection for the current thread, loop, and db path."""
    thread_id = threading.get_ident()
    loop = asyncio.get_event_loop()
    loop_id = id(loop)
    path = get_db_path(db_path)
    cache_key = (thread_id, loop_id, str(path))

    # Check if we have a cached connection and verify the loop is still valid
    if cache_key in _db_connections:
        cached_conn = _db_connections[cache_key]
        if not loop.is_closed():
            return cached_conn
        # Loop is closed, remove stale connection
        async with _db_lock:
            _db_connections.pop(cache_key, None)

    # Create new connection with async lock to prevent races
    async with _db_lock:
        # Double-check after acquiring lock
        if cache_key in _db_connections:
            return _db_connections[cache_key]

        path.parent.mkdir(parents=True, exist_ok=True)

        conn = await aiosqlite.connect(str(path))
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")

        _db_connections[cache_key] = conn

        logger.info(
            "Created new SQLite connection",
            extra={"db_path": str(path), "thread_id": thread_id, "loop_id": loop_id},
        )
        return conn


async def close_connection(*, db_path: str | None = None) -> None:
    """Close the cached SQLite connection for the current thread, loop, and db path."""
    thread_id = threading.get_ident()
    loop = asyncio.get_event_loop()
    loop_id = id(loop)
    path = get_db_path(db_path)
    cache_key = (thread_id, loop_id, str(path))

    if cache_key not in _db_connections:
        return

    try:
        async with _db_lock:
            if cache_key in _db_connections:
                conn = _db_connections[cache_key]
                await conn.close()
                del _db_connections[cache_key]
                logger.info(
                    "Closed SQLite connection",
                    extra={"thread_id": thread_id, "loop_id": loop_id, "db_path": str(path)},
                )
    except Exception as e:
        logger.warning(
            "Error closing SQLite connection",
            extra={"error": str(e), "thread_id": thread_id, "loop_id": loop_id},
        )


async def init_db(*, db_path: str | None = None) -> None:
    """Initialize the database schema by delegating to schema.init_db()."""
    schema = __import__("src.core.schema", fromlist=["init_db"])
    await schema.init_db(db_path=db_path)


async def create_record(*, collection: str, data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new record and return it with its assigned id."""
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

        logger.info("Created record", extra={"collection": collection, "record_id": record_id})
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
    """Fetch a single record by ID, raising KeyError if not found."""
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

        logger.info("Retrieved record", extra={"collection": collection, "record_id": record_id})
        return _convert_record_ids(record)
    except KeyError:
        raise
    except Exception as e:
        logger.error("get_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        msg = f"Failed to get record from {collection}: {e}"
        raise RuntimeError(msg) from e


async def update_record(*, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update a record by ID and return the updated record."""
    if not data:
        msg = "Empty update payload"
        raise ValueError(msg)

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

        logger.info("Updated record", extra={"collection": collection, "record_id": record_id})
        return await get_record(collection=collection, record_id=record_id)
    except KeyError:
        raise
    except Exception as e:
        logger.error("update_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        msg = f"Failed to update record in {collection}: {e}"
        raise RuntimeError(msg) from e


async def delete_record(*, collection: str, record_id: str) -> None:
    """Delete a record by ID, raising KeyError if not found."""
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        query = f"DELETE FROM {collection} WHERE id = ?"  # noqa: S608 - collection is validated
        cursor = await conn.execute(query, (int(record_id),))
        await conn.commit()

        if cursor.rowcount == 0:
            msg = f"Record not found in {collection}: {record_id}"
            raise KeyError(msg)

        logger.info("Deleted record", extra={"collection": collection, "record_id": record_id})
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
    """List records with optional filtering, sorting, and pagination."""
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        where_clause = ""
        params = []
        if filter_query:
            where_clause, params = parse_filter(filter_query)
            where_clause = f"WHERE {where_clause}"

        # Validate sort parameter to prevent SQL injection in ORDER BY clause
        # Only allow: column_name [ASC|DESC]
        safe_sort = "id ASC"
        if sort:
            sort_pattern = re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*(ASC|DESC)?$", sort.strip(), re.IGNORECASE)
            if sort_pattern:
                safe_sort = sort.strip()
            else:
                logger.warning("Invalid sort parameter, using default", extra={"sort": sort})

        offset = (page - 1) * per_page

        query = f"SELECT * FROM {collection} {where_clause} ORDER BY {safe_sort} LIMIT ? OFFSET ?"  # noqa: S608 - collection is validated
        params.extend([per_page, offset])

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()

        columns = [description[0] for description in cursor.description]
        records = [_convert_record_ids(dict(zip(columns, row, strict=True))) for row in rows]

        logger.info("Listed records", extra={"collection": collection, "count": len(records)})
        return records
    except Exception as e:
        logger.error("list_records_failed", extra={"collection": collection, "error": str(e)})
        msg = f"Failed to list records from {collection}: {e}"
        raise RuntimeError(msg) from e


async def get_first_record(*, collection: str, filter_query: str) -> dict[str, Any] | None:
    """Return the first record matching the filter, or None."""
    try:
        _validate_collection_name(collection)
        conn = await get_connection()

        where_clause, params = parse_filter(filter_query)

        # Guard against empty filter_query to avoid invalid WHERE clause
        if where_clause:
            query = f"SELECT * FROM {collection} WHERE {where_clause} LIMIT 1"  # noqa: S608 - collection is validated
        else:
            query = f"SELECT * FROM {collection} LIMIT 1"  # noqa: S608 - collection is validated
            params = []

        cursor = await conn.execute(query, params)
        row = await cursor.fetchone()

        if row is None:
            return None

        columns = [description[0] for description in cursor.description]
        record = dict(zip(columns, row, strict=True))

        logger.info("Retrieved first record", extra={"collection": collection})
        return _convert_record_ids(record)
    except Exception as e:
        logger.error(
            "get_first_record_failed", extra={"collection": collection, "filter_query": filter_query, "error": str(e)}
        )
        msg = f"Failed to get first record from {collection}: {e}"
        raise RuntimeError(msg) from e
