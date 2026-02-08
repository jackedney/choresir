"""Tests for InMemoryDBClient implementation."""

import pytest


# Custom exceptions replaced with standard Python exceptions


@pytest.mark.unit
class TestInMemoryDBClient:
    """Test suite for InMemoryDBClient."""

    async def test_create_record(self, in_memory_db):
        """Test creating a record."""
        data = {"name": "Test User", "email": "test@example.com"}
        record = await in_memory_db.create_record("members", data)

        assert record["id"] is not None
        assert record["name"] == "Test User"
        assert record["email"] == "test@example.com"
        assert "created" in record
        assert "updated" in record

    async def test_create_record_generates_unique_ids(self, in_memory_db):
        """Test that created records have unique IDs."""
        record1 = await in_memory_db.create_record("members", {"name": "User 1"})
        record2 = await in_memory_db.create_record("members", {"name": "User 2"})

        assert record1["id"] != record2["id"]

    async def test_create_record_invalid_data(self, in_memory_db):
        """Test creating a record with invalid data raises error."""
        with pytest.raises(RuntimeError, match="Data must be a dictionary"):
            await in_memory_db.create_record("members", "invalid")

    async def test_get_record(self, in_memory_db):
        """Test getting a record by ID."""
        created = await in_memory_db.create_record("members", {"name": "Test User"})
        record = await in_memory_db.get_record("members", created["id"])

        assert record["id"] == created["id"]
        assert record["name"] == "Test User"

    async def test_get_record_not_found(self, in_memory_db):
        """Test getting a non-existent record raises error."""
        with pytest.raises(KeyError, match="Record not found"):
            await in_memory_db.get_record("members", "nonexistent")

    async def test_get_record_invalid_id(self, in_memory_db):
        """Test getting a record with invalid ID type raises error."""
        with pytest.raises(RuntimeError, match="Record ID must be a string"):
            await in_memory_db.get_record("members", 123)

    async def test_update_record(self, in_memory_db):
        """Test updating a record."""
        created = await in_memory_db.create_record("members", {"name": "Original Name"})
        updated = await in_memory_db.update_record("members", created["id"], {"name": "Updated Name"})

        assert updated["id"] == created["id"]
        assert updated["name"] == "Updated Name"
        assert updated["updated"] != created["updated"]

    async def test_update_record_not_found(self, in_memory_db):
        """Test updating a non-existent record raises error."""
        with pytest.raises(KeyError, match="Record not found"):
            await in_memory_db.update_record("members", "nonexistent", {"name": "Test"})

    async def test_update_record_invalid_data(self, in_memory_db):
        """Test updating a record with invalid data raises error."""
        created = await in_memory_db.create_record("members", {"name": "Test"})
        with pytest.raises(RuntimeError, match="Data must be a dictionary"):
            await in_memory_db.update_record("members", created["id"], "invalid")

    async def test_delete_record(self, in_memory_db):
        """Test deleting a record."""
        created = await in_memory_db.create_record("members", {"name": "Test User"})
        result = await in_memory_db.delete_record("members", created["id"])

        assert result is True

        with pytest.raises(KeyError):
            await in_memory_db.get_record("members", created["id"])

    async def test_delete_record_not_found(self, in_memory_db):
        """Test deleting a non-existent record raises error."""
        with pytest.raises(KeyError, match="Record not found"):
            await in_memory_db.delete_record("members", "nonexistent")

    async def test_list_records_empty_collection(self, in_memory_db):
        """Test listing records from an empty collection."""
        records = await in_memory_db.list_records("members")
        assert records == []

    async def test_list_records(self, in_memory_db):
        """Test listing all records in a collection."""
        await in_memory_db.create_record("members", {"name": "User 1"})
        await in_memory_db.create_record("members", {"name": "User 2"})
        await in_memory_db.create_record("members", {"name": "User 3"})

        records = await in_memory_db.list_records("members")
        assert len(records) == 3

    async def test_list_records_with_exact_match_filter(self, in_memory_db):
        """Test filtering records with exact match."""
        await in_memory_db.create_record("members", {"name": "Alice", "status": "active"})
        await in_memory_db.create_record("members", {"name": "Bob", "status": "inactive"})
        await in_memory_db.create_record("members", {"name": "Charlie", "status": "active"})

        records = await in_memory_db.list_records("members", filter_query='status = "active"')
        assert len(records) == 2
        assert all(r["status"] == "active" for r in records)

    async def test_list_records_with_contains_filter(self, in_memory_db):
        """Test filtering records with contains operator."""
        await in_memory_db.create_record("members", {"email": "alice@gmail.com"})
        await in_memory_db.create_record("members", {"email": "bob@yahoo.com"})
        await in_memory_db.create_record("members", {"email": "charlie@gmail.com"})

        records = await in_memory_db.list_records("members", filter_query='email ~ "gmail"')
        assert len(records) == 2
        assert all("gmail" in r["email"] for r in records)

    async def test_list_records_with_not_equal_filter(self, in_memory_db):
        """Test filtering records with not equal operator."""
        await in_memory_db.create_record("members", {"name": "Alice", "status": "active"})
        await in_memory_db.create_record("members", {"name": "Bob", "status": "archived"})
        await in_memory_db.create_record("members", {"name": "Charlie", "status": "active"})

        records = await in_memory_db.list_records("members", filter_query='status != "archived"')
        assert len(records) == 2
        assert all(r["status"] != "archived" for r in records)

    async def test_list_records_with_and_filter(self, in_memory_db):
        """Test filtering records with AND conditions."""
        await in_memory_db.create_record("members", {"name": "Alice", "role": "admin", "status": "active"})
        await in_memory_db.create_record("members", {"name": "Bob", "role": "user", "status": "active"})
        await in_memory_db.create_record("members", {"name": "Charlie", "role": "admin", "status": "inactive"})

        records = await in_memory_db.list_records("members", filter_query='role = "admin" && status = "active"')
        assert len(records) == 1
        assert records[0]["name"] == "Alice"

    async def test_list_records_with_boolean_filter(self, in_memory_db):
        """Test filtering records with boolean values."""
        await in_memory_db.create_record("members", {"name": "Alice", "active": True})
        await in_memory_db.create_record("members", {"name": "Bob", "active": False})

        records = await in_memory_db.list_records("members", filter_query="active = true")
        assert len(records) == 1
        assert records[0]["name"] == "Alice"

    async def test_list_records_invalid_filter(self, in_memory_db):
        """Test that invalid filter syntax raises error."""
        await in_memory_db.create_record("members", {"name": "Test"})

        with pytest.raises(RuntimeError, match="Invalid filter syntax"):
            await in_memory_db.list_records("members", filter_query="invalid filter")

    async def test_list_records_with_ascending_sort(self, in_memory_db):
        """Test sorting records in ascending order."""
        await in_memory_db.create_record("members", {"name": "Charlie"})
        await in_memory_db.create_record("members", {"name": "Alice"})
        await in_memory_db.create_record("members", {"name": "Bob"})

        records = await in_memory_db.list_records("members", sort="name")
        assert records[0]["name"] == "Alice"
        assert records[1]["name"] == "Bob"
        assert records[2]["name"] == "Charlie"

    async def test_list_records_with_descending_sort(self, in_memory_db):
        """Test sorting records in descending order."""
        await in_memory_db.create_record("members", {"name": "Charlie"})
        await in_memory_db.create_record("members", {"name": "Alice"})
        await in_memory_db.create_record("members", {"name": "Bob"})

        records = await in_memory_db.list_records("members", sort="-name")
        assert records[0]["name"] == "Charlie"
        assert records[1]["name"] == "Bob"
        assert records[2]["name"] == "Alice"

    async def test_get_first_record(self, in_memory_db):
        """Test getting the first record matching a filter."""
        await in_memory_db.create_record("members", {"name": "Alice", "role": "admin"})
        await in_memory_db.create_record("members", {"name": "Bob", "role": "user"})
        await in_memory_db.create_record("members", {"name": "Charlie", "role": "admin"})

        record = await in_memory_db.get_first_record("members", filter_query='role = "admin"')
        assert record is not None
        assert record["role"] == "admin"

    async def test_get_first_record_no_match(self, in_memory_db):
        """Test getting first record when no match exists."""
        await in_memory_db.create_record("members", {"name": "Alice"})

        record = await in_memory_db.get_first_record("members", filter_query='name = "Bob"')
        assert record is None

    async def test_get_first_record_empty_collection(self, in_memory_db):
        """Test getting first record from empty collection."""
        record = await in_memory_db.get_first_record("members", "")
        assert record is None

    async def test_collections_are_isolated(self, in_memory_db):
        """Test that different collections are isolated from each other."""
        await in_memory_db.create_record("members", {"name": "User 1"})
        await in_memory_db.create_record("chores", {"title": "Chore 1"})

        users = await in_memory_db.list_records("members")
        chores = await in_memory_db.list_records("chores")

        assert len(users) == 1
        assert len(chores) == 1
        assert "name" in users[0]
        assert "title" in chores[0]

    async def test_record_modifications_dont_affect_storage(self, in_memory_db):
        """Test that modifying returned records doesn't affect stored data."""
        created = await in_memory_db.create_record("members", {"name": "Test User"})

        # Modify returned record
        created["name"] = "Modified"

        # Get record again - should have original value
        fetched = await in_memory_db.get_record("members", created["id"])
        assert fetched["name"] == "Test User"
