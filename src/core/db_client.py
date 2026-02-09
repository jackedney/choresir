"""aiosqlite database client wrapper with CRUD operations."""

# ruff: noqa: S608, ARG002, S105 - Table names cannot be parameterized; args and token for compatibility

import json
import logging
import re
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


def parse_filter(filter_query: str) -> tuple[str, list[Any]]:
    """Parse PocketBase-style filter query into SQL WHERE clause with parameters.

    Converts PocketBase filter syntax to parameterized SQL WHERE clause.
    Supports: =, ~ (LIKE), !=, >, <, >=, <=, && (AND), || (OR), parentheses.

    Args:
        filter_query: PocketBase filter expression

    Returns:
        Tuple of (WHERE clause string, list of bind values)

    Raises:
        ValueError: If filter syntax is invalid

    Example:
        >>> sql, params = parse_filter('name = "test" && active = true')
        >>> sql
        'name = ? AND active = ?'
        >>> params
        ['test', 1]
    """
    if not filter_query:
        return "", []

    tokens = _tokenize_filter(filter_query)
    where_clause, params, _ = _parse_expression(tokens, 0)

    if where_clause:
        return where_clause, params

    msg = f"Invalid filter syntax: {filter_query}"
    raise ValueError(msg)


def _tokenize_filter(filter_query: str) -> list[str]:
    """Tokenize filter query string into meaningful components.

    Args:
        filter_query: Filter expression string

    Returns:
        List of tokens
    """
    pattern = r"""
        \|\||&&|>=|<=|!=|>|<|=|~|
        \(|\)|
        "[^"]*"|
        '.*?'|
        [^\s"'\(\)\|\&]+
    """
    tokens = re.findall(pattern, filter_query, re.VERBOSE)
    return [token.strip() for token in tokens if token.strip()]


def _parse_expression(tokens: list[str], pos: int) -> tuple[str, list[Any], int]:
    """Parse filter expression tokens into SQL WHERE clause.

    Args:
        tokens: List of tokens
        pos: Current position in tokens

    Returns:
        Tuple of (WHERE clause string, list of bind values, next position)
    """
    if pos >= len(tokens):
        return "", [], pos

    # Parse OR expressions (lowest precedence)
    left, params, next_pos = _parse_and_expression(tokens, pos)

    if next_pos < len(tokens) and tokens[next_pos] == "||":
        next_pos += 1
        right, right_params, final_pos = _parse_expression(tokens, next_pos)
        if right:
            return f"({left} OR {right})", params + right_params, final_pos
        return left, params, next_pos

    return left, params, next_pos


def _parse_and_expression(tokens: list[str], pos: int) -> tuple[str, list[Any], int]:
    """Parse AND expression tokens.

    Args:
        tokens: List of tokens
        pos: Current position in tokens

    Returns:
        Tuple of (WHERE clause string, list of bind values, next position)
    """
    if pos >= len(tokens):
        return "", [], pos

    # Parse NOT expressions
    left, params, next_pos = _parse_not_expression(tokens, pos)

    if next_pos < len(tokens) and tokens[next_pos] == "&&":
        next_pos += 1
        right, right_params, final_pos = _parse_and_expression(tokens, next_pos)
        if right:
            return f"({left} AND {right})", params + right_params, final_pos
        return left, params, next_pos

    return left, params, next_pos


def _parse_not_expression(tokens: list[str], pos: int) -> tuple[str, list[Any], int]:
    """Parse NOT expression tokens.

    Args:
        tokens: List of tokens
        pos: Current position in tokens

    Returns:
        Tuple of (WHERE clause string, list of bind values, next position)
    """
    if pos >= len(tokens):
        return "", [], pos

    # Handle parentheses
    if tokens[pos] == "(":
        inner_pos = pos + 1
        inner, params, next_pos = _parse_expression(tokens, inner_pos)
        if next_pos < len(tokens) and tokens[next_pos] == ")":
            return f"({inner})", params, next_pos + 1

    # Parse primary expression (field operator value)
    return _parse_condition(tokens, pos)


def _parse_condition(tokens: list[str], pos: int) -> tuple[str, list[Any], int]:
    """Parse a single condition (field operator value).

    Args:
        tokens: List of tokens
        pos: Current position in tokens

    Returns:
        Tuple of (WHERE clause string, list of bind values, next position)
    """
    if pos + 2 >= len(tokens):
        return "", [], pos

    field = tokens[pos]
    operator = tokens[pos + 1]
    value_token = tokens[pos + 2]

    # Validate field name
    if not field or field in ("(", ")", "&&", "||"):
        msg = f"Invalid field name: {field}"
        raise ValueError(msg)

    # Parse value (handle quoted strings and literals)
    value = _parse_value(value_token)

    # Convert operator to SQL
    sql_operator, sql_value = _convert_operator(operator, value)

    return f"{field} {sql_operator} ?", [sql_value], pos + 3


def _parse_value(token: str) -> str:
    """Parse value token.

    Args:
        token: Value token

    Returns:
        Parsed value as string
    """
    # Handle double-quoted strings
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]

    # Handle single-quoted strings
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1]

    # Handle boolean values
    if token.lower() == "true":
        return "1"
    if token.lower() == "false":
        return "0"

    # Handle numeric values (return as is, SQLite will convert)
    if re.match(r"^-?\d+\.?\d*$", token):
        return token

    # Handle unquoted identifiers (should be quoted)
    return token


def _convert_operator(operator: str, value: str) -> tuple[str, Any]:
    """Convert PocketBase operator to SQL operator.

    Args:
        operator: PocketBase operator
        value: Value to convert if needed (for booleans)

    Returns:
        Tuple of (SQL operator, converted value)
    """
    operator_map = {
        "=": ("=", value),
        "~": ("LIKE", f"%{value}%"),
        "!=": ("!=", value),
        ">": (">", value),
        "<": ("<", value),
        ">=": (">=", value),
        "<=": ("<=", value),
    }

    if operator not in operator_map:
        msg = f"Unknown operator: {operator}"
        raise ValueError(msg)

    return operator_map[operator]


def get_db_path() -> Path:
    """Get the SQLite database path from configuration.

    Returns:
        Path to the SQLite database file
    """
    global _db_path  # noqa: PLW0603 - Singleton pattern for db path
    if _db_path is None:
        _db_path = Path(settings.sqlite_db_path)
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
        filter_query: Filter expression (PocketBase syntax)
        sort: Sort field (currently not supported, included for API compatibility)

    Returns:
        List of matching records (paginated)

    Raises:
        RuntimeError: If collection access fails
        ValueError: If filter syntax is invalid
    """
    try:
        conn = await get_connection()

        query = f"SELECT * FROM {collection}"
        params = []

        # Apply filter if provided
        if filter_query:
            where_clause, filter_params = parse_filter(filter_query)
            if where_clause:
                query += f" WHERE {where_clause}"
                params.extend(filter_params)

        # Apply sort if provided
        if sort:
            # Parse sort: "-field" for descending, "field" for ascending
            sort_field = sort.lstrip("-")
            sort_order = "DESC" if sort.startswith("-") else "ASC"
            query += f" ORDER BY {sort_field} {sort_order}"
            logger.info("Applying sort", extra={"field": sort_field, "order": sort_order})

        # Apply pagination
        offset = (page - 1) * per_page
        query += " LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        cursor = await conn.execute(query, tuple(params))
        rows = await cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in rows]
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
        filter_query: Filter expression (PocketBase syntax)

    Returns:
        First matching record or None

    Raises:
        RuntimeError: If collection access fails
        ValueError: If filter syntax is invalid
    """
    try:
        conn = await get_connection()
        query = f"SELECT * FROM {collection}"
        params = []

        # Apply filter if provided
        if filter_query:
            where_clause, filter_params = parse_filter(filter_query)
            if where_clause:
                query += f" WHERE {where_clause}"
                params.extend(filter_params)

        query += " LIMIT 1"
        cursor = await conn.execute(query, tuple(params))
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
