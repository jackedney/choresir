"""PocketBase client wrapper with CRUD operations."""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from pocketbase import PocketBase
from pocketbase.errors import ClientResponseError

from src.core.config import settings


logger = logging.getLogger(__name__)


def sanitize_param(value: str | int | float | bool | None) -> str:
    """Sanitize a value for use in PocketBase filter queries.

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
    # json.dumps handles all escaping: quotes become \", backslashes become \\
    # We strip the surrounding quotes since the caller adds them
    return json.dumps(str(value))[1:-1]


class PocketBaseConnectionPool:
    """Connection pool manager for PocketBase with health checks and automatic reconnection."""

    def __init__(
        self,
        url: str,
        admin_email: str,
        admin_password: str,
        max_retries: int = 3,
        connection_lifetime_seconds: int = 3600,  # 1 hour
    ) -> None:
        """Initialize the connection pool.

        Args:
            url: PocketBase server URL
            admin_email: Admin email for authentication
            admin_password: Admin password for authentication
            max_retries: Maximum number of retry attempts
            connection_lifetime_seconds: Maximum connection lifetime before forced reconnection
        """
        self._url = url
        self._admin_email = admin_email
        self._admin_password = admin_password
        self._max_retries = max_retries
        self._connection_lifetime = timedelta(seconds=connection_lifetime_seconds)

        self._client: PocketBase | None = None
        self._created_at: datetime | None = None

    def _create_client(self) -> PocketBase:
        """Create and authenticate a new PocketBase client."""
        logger.info("Creating new PocketBase client connection", extra={"url": self._url})
        client = PocketBase(self._url)
        client.admins.auth_with_password(self._admin_email, self._admin_password)
        self._created_at = datetime.now()
        logger.info("PocketBase client authenticated successfully")
        return client

    def _is_connection_expired(self) -> bool:
        """Check if the current connection has exceeded its lifetime."""
        if self._created_at is None:
            return True
        return datetime.now() - self._created_at > self._connection_lifetime

    def _health_check(self, client: PocketBase) -> bool:
        """Perform a health check on the client connection.

        Args:
            client: PocketBase client to check

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            # Verify token is present
            if not client.auth_store.token:
                logger.warning("PocketBase token missing")
                return False

            # Simple API call to verify connectivity
            # Using admins.auth_refresh as a lightweight health check
            client.admins.auth_refresh()
            return True
        except Exception:
            logger.exception("PocketBase health check failed")
            return False

    def _get_client_with_retry(self) -> PocketBase:
        """Get a client with exponential backoff retry logic.

        Returns:
            Authenticated PocketBase client

        Raises:
            ConnectionError: If unable to establish connection after retries
        """
        backoff_delays = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

        for attempt in range(self._max_retries):
            try:
                client = self._create_client()
                self._client = client
                logger.info(
                    "PocketBase connection established",
                    extra={"attempt": attempt + 1, "max_retries": self._max_retries},
                )
                return client
            except Exception as e:
                logger.error(
                    "PocketBase connection attempt failed",
                    extra={"attempt": attempt + 1, "max_retries": self._max_retries, "error": str(e)},
                )

                if attempt < self._max_retries - 1:
                    delay = backoff_delays[attempt]
                    logger.info("Retrying connection", extra={"delay_seconds": delay})
                    time.sleep(delay)
                else:
                    msg = f"Failed to connect to PocketBase after {self._max_retries} attempts: {e}"
                    logger.error("PocketBase connection exhausted all retries")
                    raise ConnectionError(msg) from e

        # This should never be reached, but satisfies type checker
        msg = "Unexpected error in connection retry logic"
        raise ConnectionError(msg)

    def get_client(self) -> PocketBase:
        """Get a healthy PocketBase client instance.

        Returns:
            Authenticated and healthy PocketBase client

        Raises:
            ConnectionError: If unable to establish or restore connection
        """
        # Force reconnection if lifetime exceeded
        if self._is_connection_expired():
            logger.info("PocketBase connection lifetime exceeded, forcing reconnection")
            self._client = None

        # Create new client if none exists
        if self._client is None:
            logger.info("No existing PocketBase client, creating new connection")
            return self._get_client_with_retry()

        # Health check existing client
        if not self._health_check(self._client):
            logger.warning("PocketBase health check failed, reconnecting")
            self._client = None
            return self._get_client_with_retry()

        return self._client


# Global connection pool instance
_connection_pool: PocketBaseConnectionPool | None = None


def get_client() -> PocketBase:
    """Get PocketBase client instance with admin authentication.

    Returns a healthy client from the connection pool with automatic
    reconnection, health checks, and retry logic.

    Returns:
        Authenticated PocketBase client

    Raises:
        ConnectionError: If unable to establish connection
    """
    global _connection_pool  # noqa: PLW0603

    if _connection_pool is None:
        _connection_pool = PocketBaseConnectionPool(
            url=settings.pocketbase_url,
            admin_email=settings.pocketbase_admin_email,
            admin_password=settings.pocketbase_admin_password,
        )

    return _connection_pool.get_client()


async def create_record(*, collection: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new record in the specified collection."""
    try:
        client = get_client()
        record = client.collection(collection).create(data)
        logger.info(f"Created record in {collection}: {record.id}")
        return record.__dict__
    except ClientResponseError as e:
        msg = f"Failed to create record in {collection}: {e}"
        logger.error(msg)
        raise RuntimeError(msg) from e


async def get_record(*, collection: str, record_id: str) -> dict[str, Any]:
    """Get a record by ID from the specified collection."""
    try:
        client = get_client()
        record = client.collection(collection).get_one(record_id)
        return record.__dict__
    except ClientResponseError as e:
        if e.status == 404:  # noqa: PLR2004
            msg = f"Record not found in {collection}: {record_id}"
            raise KeyError(msg) from e
        msg = f"Failed to get record from {collection}: {e}"
        logger.error(msg)
        raise RuntimeError(msg) from e


async def update_record(*, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update a record in the specified collection."""
    try:
        client = get_client()
        record = client.collection(collection).update(record_id, data)
        logger.info(f"Updated record in {collection}: {record_id}")
        return record.__dict__
    except ClientResponseError as e:
        if e.status == 404:  # noqa: PLR2004
            msg = f"Record not found in {collection}: {record_id}"
            raise KeyError(msg) from e
        msg = f"Failed to update record in {collection}: {e}"
        logger.error(msg)
        raise RuntimeError(msg) from e


async def delete_record(*, collection: str, record_id: str) -> None:
    """Delete a record from the specified collection."""
    try:
        client = get_client()
        client.collection(collection).delete(record_id)
        logger.info(f"Deleted record from {collection}: {record_id}")
    except ClientResponseError as e:
        if e.status == 404:  # noqa: PLR2004
            msg = f"Record not found in {collection}: {record_id}"
            raise KeyError(msg) from e
        msg = f"Failed to delete record from {collection}: {e}"
        logger.error(msg)
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
        client = get_client()
        # Only include filter and sort in query_params if they're not empty
        query_params = {}
        if sort:
            query_params["sort"] = sort
        if filter_query:
            query_params["filter"] = filter_query

        result = client.collection(collection).get_list(
            page=page,
            per_page=per_page,
            query_params=query_params,
        )
        return [item.__dict__ for item in result.items]
    except ClientResponseError as e:
        msg = f"Failed to list records from {collection}: {e}"
        logger.error(msg)
        raise RuntimeError(msg) from e


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
        raise RuntimeError(msg) from e


async def update_first_matching(*, collection: str, filter_query: str, data: dict[str, Any]) -> bool:
    """Update the first record matching the filter query.

    Args:
        collection: The collection to search in
        filter_query: PocketBase filter query string
        data: Dictionary of fields to update

    Returns:
        True if a record was found and updated, False if not found

    Raises:
        RuntimeError: If database operation fails

    Example:
        >>> await update_first_matching(
        ...     collection="messages",
        ...     filter_query='waha_id="msg123"',
        ...     data={"status": "delivered"}
        ... )
    """
    record = await get_first_record(collection=collection, filter_query=filter_query)
    if not record:
        return False

    await update_record(collection=collection, record_id=record["id"], data=data)
    return True
