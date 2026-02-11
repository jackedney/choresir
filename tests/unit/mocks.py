"""Pure Python in-memory database for unit testing."""

import asyncio
import copy
import re
from datetime import UTC, datetime
from typing import Any


# No longer importing custom exceptions - using Python standard exceptions


class InMemoryDBClient:
    """Pure Python in-memory database for unit testing.

    Provides a simple in-memory implementation of database operations
    without requiring a database to be running. Supports basic CRUD
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
            # Use provided ID if available, otherwise generate one
            if "id" in data:
                record_id = str(data["id"])
            else:
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

            # Ensure the final ID is used (in case data overwrites it)
            final_id = record["id"]

            # Store record using the final ID
            self._collections[collection][str(final_id)] = record

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
            filter_query: Filter expression (supports =, ~, !=, <, >, <=, >=, &&, ||)
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
            # Calculate start and end indices for the requested page
            start_index = (page - 1) * per_page
            end_index = start_index + per_page
            paginated_records = records[start_index:end_index]

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

    def _parse_filter(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate filter expression against a record.

        Supports:
        - field = "value" (exact match)
        - field != "value" (not equal)
        - field ~ "substring" (case-insensitive contains)
        - field >= "value" (greater than or equal)
        - field > "value" (greater than)
        - field <= "value" (less than or equal)
        - field < "value" (less than)
        - Multiple conditions with && (AND)
        - Multiple conditions with || (OR) - supports parentheses

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

        # Handle compound conditions (AND, OR, parentheses)
        compound_result = self._evaluate_compound_conditions(filter_str, record)
        if compound_result is not None:
            return compound_result

        # Remove parentheses if present (for simple single conditions in parens)
        if filter_str.startswith("(") and filter_str.endswith(")"):
            filter_str = filter_str[1:-1].strip()

        # Parse single condition with comparison operators
        return self._evaluate_single_condition(filter_str, record)

    def _evaluate_compound_conditions(self, filter_str: str, record: dict[str, Any]) -> bool | None:
        """Evaluate compound conditions (AND, OR, parentheses).

        Returns:
            True/False if compound condition was evaluated, None if not a compound condition.
        """
        # Handle AND conditions first (before handling OR/parentheses)
        if "&&" in filter_str:
            return self._evaluate_and_conditions(filter_str, record)

        # Handle OR conditions (check for || outside of parentheses)
        if "||" in filter_str and "(" not in filter_str:
            return self._evaluate_or_conditions(filter_str, record)

        # Handle parentheses with OR conditions
        if "(" in filter_str and "||" in filter_str:
            return self._evaluate_parentheses(filter_str, record)

        return None

    def _evaluate_and_conditions(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate AND (&&) conditions."""
        conditions = [c.strip() for c in filter_str.split("&&")]
        return all(self._parse_filter(cond, record) for cond in conditions)

    def _evaluate_or_conditions(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate OR (||) conditions."""
        conditions = [c.strip() for c in filter_str.split("||")]
        return any(self._parse_filter(cond, record) for cond in conditions)

    def _evaluate_parentheses(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate parenthesized OR conditions like (field = 'val1' || field = 'val2')."""
        match = re.search(r"\(([^)]+)\)", filter_str)
        if match:
            inner = match.group(1)
            or_conditions = [c.strip() for c in inner.split("||")]
            return any(self._parse_filter(cond, record) for cond in or_conditions)
        return False

    def _evaluate_single_condition(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate a single comparison condition."""
        # Operators ordered by length (longest first) to avoid partial matches
        # e.g., ">=" must be checked before ">"
        operators = [">=", "<=", "!=", ">", "<", "~", "="]
        comparators = {
            ">=": self._compare_gte,
            "<=": self._compare_lte,
            "!=": self._compare_neq,
            ">": self._compare_gt,
            "<": self._compare_lt,
            "~": self._compare_contains,
            "=": self._compare_eq,
        }

        for op in operators:
            if op in filter_str:
                return comparators[op](filter_str, record)

        raise RuntimeError(f"Invalid filter syntax (no operator found): {filter_str}")

    def _parse_comparison(self, filter_str: str, operator: str) -> tuple[str, str]:
        """Parse a comparison into field and value parts."""
        parts = filter_str.split(operator, 1)
        if len(parts) != 2:
            raise RuntimeError(f"Invalid filter syntax: {filter_str}")
        field = parts[0].strip()
        value = parts[1].strip().strip("'\"")
        return field, value

    def _compare_gte(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate >= comparison."""
        field, value = self._parse_comparison(filter_str, ">=")
        return str(record.get(field, "")) >= value

    def _compare_lte(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate <= comparison."""
        field, value = self._parse_comparison(filter_str, "<=")
        return str(record.get(field, "")) <= value

    def _compare_neq(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate != comparison."""
        field, value = self._parse_comparison(filter_str, "!=")
        return str(record.get(field, "")) != value

    def _compare_gt(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate > comparison."""
        field, value = self._parse_comparison(filter_str, ">")
        return str(record.get(field, "")) > value

    def _compare_lt(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate < comparison."""
        field, value = self._parse_comparison(filter_str, "<")
        return str(record.get(field, "")) < value

    def _compare_contains(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate ~ (case-insensitive contains) comparison."""
        field, value = self._parse_comparison(filter_str, "~")
        return value.lower() in str(record.get(field, "")).lower()

    def _compare_eq(self, filter_str: str, record: dict[str, Any]) -> bool:
        """Evaluate = (exact match) comparison."""
        field, value = self._parse_comparison(filter_str, "=")

        # Handle boolean values
        if value.lower() in ("true", "false"):
            return record.get(field) == (value.lower() == "true")

        return str(record.get(field, "")) == value

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

        # Support both "-field" and "field DESC" conventions
        sort = sort.strip()
        if sort.startswith("-"):
            reverse = True
            field = sort[1:]
        elif sort.upper().endswith(" DESC"):
            reverse = True
            field = sort[: -len(" DESC")].strip()
        elif sort.upper().endswith(" ASC"):
            reverse = False
            field = sort[: -len(" ASC")].strip()
        else:
            reverse = False
            field = sort

        # Sort by field, handling missing fields
        return sorted(
            records,
            key=lambda r: r.get(field, ""),
            reverse=reverse,
        )
