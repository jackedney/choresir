"""PocketBase client wrapper with CRUD operations."""

import logging
from typing import Any, TypeVar

from pocketbase import PocketBase
from pocketbase.client import ClientResponseError

from src.core.config import settings


logger = logging.getLogger(__name__)
T = TypeVar("T")


class DatabaseError(Exception):
    """Base exception for database operations."""


class RecordNotFoundError(DatabaseError):
    """Raised when a record is not found."""


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""


def get_client() -> PocketBase:
    """Get PocketBase client instance."""
    try:
        return PocketBase(settings.pocketbase_url)
    except Exception as e:
        msg = f"Failed to connect to PocketBase: {e}"
        logger.error(msg)
        raise DatabaseConnectionError(msg) from e


async def create_record(*, collection: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new record in the specified collection."""
    try:
        client = get_client()
        record = client.collection(collection).create(data)
        logger.info("Created record in %s: %s", collection, record.id)
        return record.__dict__
    except ClientResponseError as e:
        msg = f"Failed to create record in {collection}: {e}"
        logger.error(msg)
        raise DatabaseError(msg) from e


async def get_record(*, collection: str, record_id: str) -> dict[str, Any]:
    """Get a record by ID from the specified collection."""
    try:
        client = get_client()
        record = client.collection(collection).get_one(record_id)
        return record.__dict__
    except ClientResponseError as e:
        if e.status == 404:  # noqa: PLR2004
            msg = f"Record not found in {collection}: {record_id}"
            raise RecordNotFoundError(msg) from e
        msg = f"Failed to get record from {collection}: {e}"
        logger.error(msg)
        raise DatabaseError(msg) from e


async def update_record(*, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update a record in the specified collection."""
    try:
        client = get_client()
        record = client.collection(collection).update(record_id, data)
        logger.info("Updated record in %s: %s", collection, record_id)
        return record.__dict__
    except ClientResponseError as e:
        if e.status == 404:  # noqa: PLR2004
            msg = f"Record not found in {collection}: {record_id}"
            raise RecordNotFoundError(msg) from e
        msg = f"Failed to update record in {collection}: {e}"
        logger.error(msg)
        raise DatabaseError(msg) from e


async def delete_record(*, collection: str, record_id: str) -> None:
    """Delete a record from the specified collection."""
    try:
        client = get_client()
        client.collection(collection).delete(record_id)
        logger.info("Deleted record from %s: %s", collection, record_id)
    except ClientResponseError as e:
        if e.status == 404:  # noqa: PLR2004
            msg = f"Record not found in {collection}: {record_id}"
            raise RecordNotFoundError(msg) from e
        msg = f"Failed to delete record from {collection}: {e}"
        logger.error(msg)
        raise DatabaseError(msg) from e


async def list_records(
    *,
    collection: str,
    page: int = 1,
    per_page: int = 50,
    filter_query: str = "",
    sort: str = "-created",
) -> list[dict[str, Any]]:
    """List records from the specified collection with filtering and pagination."""
    try:
        client = get_client()
        result = client.collection(collection).get_list(
            page=page,
            per_page=per_page,
            query_params={"filter": filter_query, "sort": sort},
        )
        return [item.__dict__ for item in result.items]
    except ClientResponseError as e:
        msg = f"Failed to list records from {collection}: {e}"
        logger.error(msg)
        raise DatabaseError(msg) from e


async def get_first_record(*, collection: str, filter_query: str) -> dict[str, Any] | None:
    """Get the first record matching the filter query, or None if not found."""
    try:
        client = get_client()
        result = client.collection(collection).get_first_list_item(filter_query)
        return result.__dict__
    except ClientResponseError as e:
        if e.status == 404:  # noqa: PLR2004
            return None
        msg = f"Failed to get first record from {collection}: {e}"
        logger.error(msg)
        raise DatabaseError(msg) from e
