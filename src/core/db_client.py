"""aiosqlite database client wrapper with CRUD operations."""

# ruff: noqa: S608, ARG002, S105 - Table names cannot be parameterized; args and token for compatibility

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from src.core.config import settings
from src.core.schema import TABLES, init_db as schema_init_db


logger = logging.getLogger(__name__)

# Database connection singleton
_db_path: Path | None = None
_db_connection: aiosqlite.Connection | None = None


def get_db_path() -> Path:
    """Get the SQLite database path from configuration.

    Returns:
        Path to the SQLite database file
    """
    global _db_path  # noqa: PLW0603 - Singleton pattern for db path
    if _db_path is None:
        # Use data directory for database storage
        db_path = settings.pocketbase_url  # TODO: Replace with sqlite_db_path config in US-005
        if db_path.startswith("http://") or db_path.startswith("https://"):
            # Temporary: use local data directory until US-005 adds sqlite_db_path config
            db_dir = Path(__file__).parent.parent.parent / "data"
            db_dir.mkdir(exist_ok=True)
            _db_path = db_dir / "choresir.db"
        else:
            _db_path = Path(db_path)
    return _db_path


async def get_connection() -> aiosqlite.Connection:
    """Get a connection to the SQLite database.

    Returns:
        aiosqlite connection object

    Raises:
        RuntimeError: If connection cannot be established
    """
    global _db_connection  # noqa: PLW0603 - Singleton pattern for db connection
    if _db_connection is None:
        try:
            db_path = get_db_path()
            _db_connection = await aiosqlite.connect(db_path)
            await _db_connection.execute("PRAGMA foreign_keys = ON")
            await _db_connection.execute("PRAGMA journal_mode = WAL")
            logger.info("Connected to SQLite database", extra={"path": str(db_path)})
        except Exception as e:
            msg = f"Failed to connect to database: {e}"
            logger.error("Database connection failed", extra={"error": str(e)})
            raise RuntimeError(msg) from e
    return _db_connection


async def close_connection() -> None:
    """Close the database connection if open."""
    global _db_connection  # noqa: PLW0603 - Singleton pattern for db connection
    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None
        logger.info("Database connection closed")


def sanitize_param(value: str | int | float | bool | None) -> str:
    """Sanitize a value for use in SQLite filter queries.

    Uses json.dumps to properly escape quotes and backslashes, preventing
    filter injection attacks. The result is safe to embed in filter strings.

    Args:
        value: The value to sanitize (will be converted to string)

    Returns:
        A properly escaped string value (without surrounding quotes)

    Example:
        >>> phone = 'foo" || true || "'
        >>> filter_query = f'phone = "{sanitize_param(phone)}"'
        # Results in: phone = "foo\" || true || \""
        # Which safely treats the injection attempt as a literal string
    """
    return json.dumps(str(value))[1:-1]


async def init_db() -> None:
    """Initialize the database tables for all collections.

    Creates tables for all collections defined in src/core/schema.py if they don't exist.
    Uses CREATE TABLE IF NOT EXISTS to make this idempotent.

    Raises:
        RuntimeError: If table creation fails
    """
    try:
        await schema_init_db()
        logger.info("Database tables initialized successfully", extra={"tables": TABLES})
    except Exception as e:
        msg = f"Failed to initialize database: {e}"
        logger.error("Database initialization failed", extra={"error": str(e)})
        raise RuntimeError(msg) from e


def _build_column_list(data: dict[str, Any]) -> list[str]:
    """Build column list for INSERT queries.

    Args:
        data: Record data

    Returns:
        List of column names
    """
    return ["id", "created", "updated", *list(data.keys())]


def _build_insert_query(table_name: str, columns: list[str]) -> str:
    """Build INSERT query with placeholders.

    Args:
        table_name: Name of the table
        columns: List of column names

    Returns:
        SQL INSERT query with placeholders
    """
    placeholders = ", ".join(["?" for _ in columns])
    column_names = ", ".join(columns)
    return f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"


def _build_update_query(table_name: str, data_columns: list[str]) -> str:
    """Build UPDATE query with placeholders.

    Args:
        table_name: Name of the table
        data_columns: List of column names to update (excluding id, created, updated)

    Returns:
        SQL UPDATE query with placeholders
    """
    set_clauses = ", ".join([f"{col} = ?" for col in [*data_columns, "updated"]])
    return f"UPDATE {table_name} SET {set_clauses} WHERE id = ?"


async def create_record(*, collection: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new record in the specified collection.

    Args:
        collection: Name of the collection/table
        data: Record data to store

    Returns:
        Created record with id, created, and updated timestamps

    Raises:
        RuntimeError: If collection access fails or table doesn't exist
    """
    try:
        conn = await get_connection()
        record_id = uuid.uuid4().hex[:15]
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        columns = _build_column_list(data)
        values = [record_id, now, now, *list(data.values())]

        query = _build_insert_query(collection, columns)
        await conn.execute(query, tuple(values))
        await conn.commit()

        logger.info("Created record in %s: %s", collection, record_id)

        return await get_record(collection=collection, record_id=record_id)
    except aiosqlite.OperationalError as e:
        if "no such table" in str(e):
            msg = f"Table {collection} does not exist. Call init_db() first."
            logger.error("Table not found", extra={"collection": collection, "error": str(e)})
            raise RuntimeError(msg) from e
        msg = f"Failed to create record in {collection}: {e}"
        logger.error("create_record_failed", extra={"collection": collection, "error": str(e)})
        raise RuntimeError(msg) from e
    except Exception as e:
        msg = f"Failed to create record in {collection}: {e}"
        logger.error("create_record_failed", extra={"collection": collection, "error": str(e)})
        raise RuntimeError(msg) from e


async def get_record(*, collection: str, record_id: str) -> dict[str, Any]:
    """Get a record by ID from the specified collection.

    Args:
        collection: Name of the collection/table
        record_id: ID of the record to retrieve

    Returns:
        The requested record

    Raises:
        KeyError: If record not found
        RuntimeError: If collection access fails
    """
    try:
        conn = await get_connection()
        cursor = await conn.execute(
            f"SELECT * FROM {collection} WHERE id = ?",
            (record_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            msg = f"Record not found in {collection}: {record_id}"
            logger.warning("Record not found", extra={"collection": collection, "record_id": record_id})
            raise KeyError(msg)

        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row, strict=False))
    except aiosqlite.OperationalError as e:
        if "no such table" in str(e):
            msg = f"Table {collection} does not exist. Call init_db() first."
            logger.error("Table not found", extra={"collection": collection, "error": str(e)})
            raise RuntimeError(msg) from e
        msg = f"Failed to get record from {collection}: {e}"
        logger.error("get_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        raise RuntimeError(msg) from e
    except KeyError:
        raise
    except Exception as e:
        msg = f"Failed to get record from {collection}: {e}"
        logger.error("get_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        raise RuntimeError(msg) from e


async def update_record(*, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update a record in the specified collection.

    Args:
        collection: Name of the collection/table
        record_id: ID of the record to update
        data: Data to update

    Returns:
        Updated record

    Raises:
        KeyError: If record not found
        RuntimeError: If collection access fails
    """
    try:
        conn = await get_connection()
        cursor = await conn.execute(
            f"SELECT id FROM {collection} WHERE id = ?",
            (record_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            msg = f"Record not found in {collection}: {record_id}"
            logger.warning("Record not found", extra={"collection": collection, "record_id": record_id})
            raise KeyError(msg)

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        data_columns = list(data.keys())
        values = [*list(data.values()), now, record_id]

        query = _build_update_query(collection, data_columns)

        await conn.execute(query, tuple(values))
        await conn.commit()

        logger.info("Updated record in %s: %s", collection, record_id)

        return await get_record(collection=collection, record_id=record_id)
    except aiosqlite.OperationalError as e:
        if "no such table" in str(e):
            msg = f"Table {collection} does not exist. Call init_db() first."
            logger.error("Table not found", extra={"collection": collection, "error": str(e)})
            raise RuntimeError(msg) from e
        msg = f"Failed to update record in {collection}: {e}"
        logger.error("update_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        raise RuntimeError(msg) from e
    except KeyError:
        raise
    except Exception as e:
        msg = f"Failed to update record in {collection}: {e}"
        logger.error("update_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        raise RuntimeError(msg) from e


async def delete_record(*, collection: str, record_id: str) -> None:
    """Delete a record from the specified collection.

    Args:
        collection: Name of the collection/table
        record_id: ID of the record to delete

    Raises:
        KeyError: If record not found
        RuntimeError: If collection access fails
    """
    try:
        conn = await get_connection()
        cursor = await conn.execute(
            f"SELECT id FROM {collection} WHERE id = ?",
            (record_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            msg = f"Record not found in {collection}: {record_id}"
            logger.warning("Record not found", extra={"collection": collection, "record_id": record_id})
            raise KeyError(msg)

        conn.execute(
            f"DELETE FROM {collection} WHERE id = ?",
            (record_id,),
        )
        await conn.commit()

        logger.info("Deleted record from %s: %s", collection, record_id)
    except aiosqlite.OperationalError as e:
        if "no such table" in str(e):
            msg = f"Table {collection} does not exist. Call init_db() first."
            logger.error("Table not found", extra={"collection": collection, "error": str(e)})
            raise RuntimeError(msg) from e
        msg = f"Failed to delete record in {collection}: {e}"
        logger.error("delete_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        raise RuntimeError(msg) from e
    except KeyError:
        raise
    except Exception as e:
        msg = f"Failed to delete record in {collection}: {e}"
        logger.error("delete_record_failed", extra={"collection": collection, "record_id": record_id, "error": str(e)})
        raise RuntimeError(msg) from e


async def list_records(
    *,
    collection: str,
    page: int = 1,
    per_page: int = 50,
    filter_query: str = "",
    sort: str = "",
) -> list[dict[str, Any]]:
    """List records from the specified collection with filtering and pagination.

    Args:
        collection: Name of the collection/table
        page: Page number (1-indexed)
        per_page: Number of records per page
        filter_query: Filter expression (currently not supported, included for API compatibility)
        sort: Sort field (currently not supported, included for API compatibility)

    Returns:
        List of matching records (paginated)

    Raises:
        RuntimeError: If collection access fails
    """
    try:
        conn = await get_connection()

        # Build query with pagination
        query = f"SELECT * FROM {collection}"
        params = []

        # Apply pagination
        offset = (page - 1) * per_page
        query += " LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        cursor = await conn.execute(query, tuple(params))
        rows = await cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        records = [dict(zip(columns, row, strict=False)) for row in rows]

        # TODO: Implement filter_query and sort in US-003
        if filter_query:
            logger.warning("filter_query not yet implemented in SQLite backend", extra={"filter": filter_query})
        if sort:
            logger.warning("sort not yet implemented in SQLite backend", extra={"sort": sort})

        return records
    except aiosqlite.OperationalError as e:
        if "no such table" in str(e):
            msg = f"Table {collection} does not exist. Call init_db() first."
            logger.error("Table not found", extra={"collection": collection, "error": str(e)})
            raise RuntimeError(msg) from e
        msg = f"Failed to list records from {collection}: {e}"
        logger.error("list_records_failed", extra={"collection": collection, "error": str(e)})
        raise RuntimeError(msg) from e
    except Exception as e:
        msg = f"Failed to list records from {collection}: {e}"
        logger.error("list_records_failed", extra={"collection": collection, "error": str(e)})
        raise RuntimeError(msg) from e


async def get_first_record(*, collection: str, filter_query: str) -> dict[str, Any] | None:
    """Get the first record matching the filter query, or None if not found.

    Args:
        collection: Name of the collection/table
        filter_query: Filter expression (currently not supported)

    Returns:
        First matching record or None

    Raises:
        RuntimeError: If collection access fails
    """
    try:
        # TODO: Implement filter_query in US-003
        if filter_query:
            logger.warning("filter_query not yet implemented in SQLite backend", extra={"filter": filter_query})

        conn = await get_connection()
        cursor = await conn.execute(f"SELECT * FROM {collection} LIMIT 1")
        row = await cursor.fetchone()

        if row is None:
            return None

        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row, strict=False))
    except aiosqlite.OperationalError as e:
        if "no such table" in str(e):
            msg = f"Table {collection} does not exist. Call init_db() first."
            logger.error("Table not found", extra={"collection": collection, "error": str(e)})
            raise RuntimeError(msg) from e
        msg = f"Failed to get first record from {collection}: {e}"
        logger.error(
            "get_first_record_failed", extra={"collection": collection, "filter_query": filter_query, "error": str(e)}
        )
        raise RuntimeError(msg) from e
    except Exception as e:
        msg = f"Failed to get first record from {collection}: {e}"
        logger.error(
            "get_first_record_failed", extra={"collection": collection, "filter_query": filter_query, "error": str(e)}
        )
        raise RuntimeError(msg) from e


class _DBClient:
    """Mock client object for backward compatibility with old PocketBase client pattern.

    This provides minimal compatibility with code that expects a client object.
    The real operations use direct functions from this module.
    """

    class _AuthStore:
        """Mock auth store for PocketBase compatibility."""

        def __init__(self) -> None:
            self.token = "BACKWARD_COMPAT_TOKEN_PLACEHOLDER"

    def __init__(self) -> None:
        self.auth_store = _DBClient._AuthStore()

    def get_first_record(
        self,
        collection: str,
        filter_query: str,
    ) -> dict[str, Any] | None:
        """Get first record matching filter.

        This is a compatibility wrapper. Real code uses async module functions.
        """
        raise RuntimeError("Use async db_client.get_first_record() instead of client.get_first_record()")


def get_client() -> _DBClient:
    """Get database client for backward compatibility.

    This was previously a PocketBase client. Now returns a mock object
    to maintain API compatibility. Real operations should use the async
    module functions directly (create_record, get_record, etc.).

    Returns:
        Mock database client object
    """
    return _DBClient()


# Backward compatibility: alias _DBClient as PocketBase for type checking
# TODO: Remove after US-006 updates all code to use async module functions
PocketBase = _DBClient
