"""Pure Python in-memory database for unit testing."""

import asyncio
import copy
from datetime import UTC, datetime
from typing import Any


# No longer importing custom exceptions - using Python standard exceptions


class InMemoryDBClient:
    """Pure Python in-memory database for unit testing.

    Provides a simple in-memory implementation of database operations
    without requiring PocketBase to be running. Supports basic CRUD
    operations and simple filtering/sorting.
    """

    def __init__(self):
        """Initialize empty in-memory database."""
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}
        self._id_counter = 1000

    async def create_record(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new record in the specified collection.

        Args:
            collection: Name of the collection
            data: Record data to store

        Returns:
            Created record with id, created, and updated timestamps

        Raises:
            RuntimeError: If collection access fails
        """
        if not isinstance(data, dict):
            raise RuntimeError(f"Data must be a dictionary, got {type(data)}")

        try:
            # Ensure collection exists
            if collection not in self._collections:
                self._collections[collection] = {}

            # Generate ID and timestamps
            record_id = str(self._id_counter)
            self._id_counter += 1

            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

            # Create full record
            record = {
                "id": record_id,
                "created": now,
                "updated": now,
                **data,
            }

            # Store record
            self._collections[collection][record_id] = record

            return copy.deepcopy(record)
        except Exception as e:
            raise RuntimeError(f"Failed to create record in {collection}: {e}") from e

    async def get_record(self, collection: str, record_id: str) -> dict[str, Any]:
        """Get a record by ID from the specified collection.

        Args:
            collection: Name of the collection
            record_id: ID of the record to retrieve

        Returns:
            The requested record

        Raises:
            KeyError: If record not found
            RuntimeError: For other failures
        """
        if not isinstance(record_id, str):
            raise RuntimeError(f"Record ID must be a string, got {type(record_id)}")

        try:
            if collection not in self._collections:
                raise KeyError(f"Record not found in {collection}: {record_id}")

            if record_id not in self._collections[collection]:
                raise KeyError(f"Record not found in {collection}: {record_id}")

            return copy.deepcopy(self._collections[collection][record_id])
        except KeyError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to get record from {collection}: {e}") from e

    async def update_record(self, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing record.

        Args:
            collection: Name of the collection
            record_id: ID of the record to update
            data: Data to update

        Returns:
            Updated record

        Raises:
            KeyError: If record not found
            RuntimeError: For other failures
        """
        if not isinstance(data, dict):
            raise RuntimeError(f"Data must be a dictionary, got {type(data)}")

        if not isinstance(record_id, str):
            raise RuntimeError(f"Record ID must be a string, got {type(record_id)}")

        try:
            if collection not in self._collections:
                raise KeyError(f"Record not found in {collection}: {record_id}")

            if record_id not in self._collections[collection]:
                raise KeyError(f"Record not found in {collection}: {record_id}")

            # Update record
            # Add small delay to ensure updated timestamp differs from created
            await asyncio.sleep(0.001)
            record = self._collections[collection][record_id]
            record.update(data)
            record["updated"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

            return copy.deepcopy(record)
        except KeyError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to update record in {collection}: {e}") from e

    async def delete_record(self, collection: str, record_id: str) -> bool:
        """Delete a record from the collection.

        Args:
            collection: Name of the collection
            record_id: ID of the record to delete

        Returns:
            True on success

        Raises:
            KeyError: If record not found
        """
        if not isinstance(record_id, str):
            raise RuntimeError(f"Record ID must be a string, got {type(record_id)}")

        if collection not in self._collections:
            raise KeyError(f"Record not found in {collection}: {record_id}")

        if record_id not in self._collections[collection]:
            raise KeyError(f"Record not found in {collection}: {record_id}")

        del self._collections[collection][record_id]
        return True

    async def list_records(
        self,
        collection: str,
        page: int = 1,
        per_page: int = 50,
        filter_query: str = "",
        sort: str = "",
    ) -> list[dict[str, Any]]:
        """List records from the collection with optional filtering and sorting.

        Args:
            collection: Name of the collection
            page: Page number (1-indexed)
            per_page: Number of records per page
            filter_query: Filter expression (supports =, ~, !=)
            sort: Sort field (prefix with - for descending)

        Returns:
            List of matching records (paginated)

        Raises:
            RuntimeError: For invalid filter syntax
        """
        try:
            # Return empty list if collection doesn't exist
            if collection not in self._collections:
                return []

            # Get all records
            records = list(self._collections[collection].values())

            # Apply filter if provided
            if filter_query:
                records = [r for r in records if self._parse_filter(filter_query, r)]

            # Apply sort if provided
            if sort:
                records = self._apply_sort(records, sort)

            # Apply pagination
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_records = records[start_idx:end_idx]

            # Return deep copies to prevent external modifications
            return [copy.deepcopy(r) for r in paginated_records]
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to list records from {collection}: {e}") from e

    async def get_first_record(self, collection: str, filter_query: str) -> dict[str, Any] | None:
        """Get the first matching record or None.

        Args:
            collection: Name of the collection
            filter_query: Filter expression (supports =, ~, !=)

        Returns:
            First matching record or None
        """
        records = await self.list_records(collection, filter_query=filter_query)
        return records[0] if records else None

    def _parse_filter(self, filter_str: str, record: dict[str, Any]) -> bool:  # noqa: C901, PLR0911, PLR0912, PLR0915
        """Evaluate filter expression against a record.

        Supports:
        - field = "value" (exact match)
        - field != "value" (not equal)
        - field ~ "substring" (case-insensitive contains, matching PocketBase)
        - field >= "value" (greater than or equal)
        - field > "value" (greater than)
        - field <= "value" (less than or equal)
        - field < "value" (less than)
        - Multiple conditions with && (AND)
        - Multiple conditions with || (OR)
        - Parentheses for grouping: (condition1 || condition2)

        Args:
            filter_str: Filter expression
            record: Record to evaluate

        Returns:
            True if record matches filter

        Raises:
            RuntimeError: For invalid filter syntax
        """
        if not filter_str:
            return True

        # Handle parentheses - extract and evaluate grouped conditions
        if "(" in filter_str and ")" in filter_str:
            # Simple parenthesis handling - extract the content and evaluate
            import re

            match = re.search(r"\((.*?)\)", filter_str)
            if match:
                grouped_expr = match.group(1)
                grouped_result = self._parse_filter(grouped_expr, record)

                # Check if there are remaining conditions outside the parentheses
                before = filter_str[: match.start()].strip()
                after = filter_str[match.end() :].strip()

                # If there are AND/OR operations before or after, handle them
                if before or after:
                    # Remove empty operators
                    if before.endswith("&&") or before.endswith("||"):
                        operator = "&&" if before.endswith("&&") else "||"
                        before = before[:-2].strip()
                    elif after.startswith("&&") or after.startswith("||"):
                        operator = "&&" if after.startswith("&&") else "||"
                        after = after[2:].strip()
                    else:
                        # No explicit operator, return just the grouped result
                        return grouped_result

                    # Evaluate remaining conditions
                    if before and after:
                        # Both before and after
                        if operator == "&&":
                            return (
                                self._parse_filter(before, record)
                                and grouped_result
                                and self._parse_filter(after, record)
                            )
                        return self._parse_filter(before, record) or grouped_result or self._parse_filter(after, record)
                    if before:
                        if operator == "&&":
                            return self._parse_filter(before, record) and grouped_result
                        return self._parse_filter(before, record) or grouped_result
                    if after:
                        if operator == "&&":
                            return grouped_result and self._parse_filter(after, record)
                        return grouped_result or self._parse_filter(after, record)

                # Otherwise return the grouped result
                return grouped_result

        # Handle AND conditions (higher precedence than OR)
        if "&&" in filter_str:
            # Split by && but not within parentheses
            conditions = [c.strip() for c in filter_str.split("&&")]
            return all(self._parse_filter(cond, record) for cond in conditions)

        # Handle OR conditions
        if "||" in filter_str:
            conditions = [c.strip() for c in filter_str.split("||")]
            return any(self._parse_filter(cond, record) for cond in conditions)

        # Parse single condition - try comparison operators (longer first)
        if ">=" in filter_str:
            parts = filter_str.split(">=", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid filter syntax: {filter_str}")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")
            record_value = str(record.get(field, ""))
            return record_value >= value

        if "<=" in filter_str:
            parts = filter_str.split("<=", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid filter syntax: {filter_str}")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")
            record_value = str(record.get(field, ""))
            return record_value <= value

        # Try != operator (before =)
        if "!=" in filter_str:
            parts = filter_str.split("!=", 1)
            if len(parts) != 2:
                raise RuntimeError(f"Invalid filter syntax: {filter_str}")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")
            return str(record.get(field, "")) != value

        # Try > operator
        if ">" in filter_str:
            parts = filter_str.split(">", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid filter syntax: {filter_str}")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")
            record_value = str(record.get(field, ""))
            return record_value > value

        # Try < operator
        if "<" in filter_str:
            parts = filter_str.split("<", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid filter syntax: {filter_str}")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")
            record_value = str(record.get(field, ""))
            return record_value < value

        # Try ~ operator (case-insensitive contains, matching PocketBase behavior)
        if "~" in filter_str:
            parts = filter_str.split("~", 1)
            if len(parts) != 2:
                raise RuntimeError(f"Invalid filter syntax: {filter_str}")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")
            return value.lower() in str(record.get(field, "")).lower()

        # Try = operator (exact match)
        if "=" in filter_str:
            parts = filter_str.split("=", 1)
            if len(parts) != 2:
                raise RuntimeError(f"Invalid filter syntax: {filter_str}")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")

            # Handle boolean values
            if value.lower() in ("true", "false"):
                return record.get(field) == (value.lower() == "true")

            return str(record.get(field, "")) == value

        raise RuntimeError(f"Invalid filter syntax (no operator found): {filter_str}")

    def _apply_sort(self, records: list[dict], sort: str) -> list[dict]:
        """Sort records by field.

        Args:
            records: Records to sort
            sort: Sort field (prefix with - for descending)

        Returns:
            Sorted records
        """
        if not sort:
            return records

        # Check for descending sort
        reverse = sort.startswith("-")
        field = sort[1:] if reverse else sort

        # Sort by field, handling missing fields
        return sorted(
            records,
            key=lambda r: r.get(field, ""),
            reverse=reverse,
        )
