"""Unit tests for pantry_service module."""

import pytest

from src.domain.pantry import PantryItemStatus
from src.services import pantry_service
from tests.unit.conftest import DatabaseClient


@pytest.fixture
def patched_pantry_db(mock_db_module_for_unit_tests, db_client):
    """Patches settings and database for pantry service tests.

    Uses real SQLite database via db_client fixture from tests/conftest.py.
    Settings are patched by mock_db_module_for_unit_tests fixture.
    """
    return DatabaseClient()


@pytest.fixture
async def sample_user_id(patched_pantry_db):
    """Sample user ID for testing - creates a real member in the database."""
    user = await patched_pantry_db.create_record(
        collection="members",
        data={
            "name": "Test User",
            "phone": "+19999999999",
            "role": "member",
            "status": "active",
        },
    )
    return str(user["id"])


@pytest.mark.unit
class TestAddToShoppingList:
    """Tests for add_to_shopping_list function."""

    async def test_add_item_success(self, patched_pantry_db, sample_user_id):
        """Test adding a new item to shopping list."""
        result = await pantry_service.add_to_shopping_list(
            item_name="Milk",
            user_id=sample_user_id,
        )

        assert result["item_name"] == "Milk"
        assert result["added_by"] == sample_user_id
        assert "id" in result
        assert "added_at" in result

    async def test_add_item_with_quantity_and_notes(self, patched_pantry_db, sample_user_id):
        """Test adding item with optional fields."""
        result = await pantry_service.add_to_shopping_list(
            item_name="Eggs",
            user_id=sample_user_id,
            quantity=12,
            notes="organic, large",
        )

        assert result["item_name"] == "Eggs"
        assert result["quantity"] == 12
        assert result["notes"] == "organic, large"

    async def test_add_duplicate_item_updates_quantity(self, patched_pantry_db, sample_user_id):
        """Test adding duplicate item updates quantity."""
        # Add first item
        await pantry_service.add_to_shopping_list(
            item_name="Milk",
            user_id=sample_user_id,
            quantity=1,
        )

        # Add same item again
        result = await pantry_service.add_to_shopping_list(
            item_name="Milk",
            user_id=sample_user_id,
            quantity=2,
        )

        # Should have combined quantity
        assert result["quantity"] == 3

    async def test_add_item_case_insensitive(self, patched_pantry_db, sample_user_id):
        """Test adding item is case-insensitive for matching."""
        await pantry_service.add_to_shopping_list(
            item_name="milk",
            user_id=sample_user_id,
            quantity=1,
        )

        result = await pantry_service.add_to_shopping_list(
            item_name="MILK",
            user_id=sample_user_id,
            quantity=2,
        )

        # Should update existing item
        assert result["quantity"] == 3


@pytest.mark.unit
class TestGetShoppingList:
    """Tests for get_shopping_list function."""

    async def test_get_empty_list(self, patched_pantry_db):
        """Test getting empty shopping list."""
        result = await pantry_service.get_shopping_list()

        assert result == []

    async def test_get_list_with_items(self, patched_pantry_db, sample_user_id):
        """Test getting shopping list with items."""
        # Add some items
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)
        await pantry_service.add_to_shopping_list(item_name="Eggs", user_id=sample_user_id)
        await pantry_service.add_to_shopping_list(item_name="Bread", user_id=sample_user_id)

        result = await pantry_service.get_shopping_list()

        assert len(result) == 3
        item_names = [item["item_name"] for item in result]
        assert "Milk" in item_names
        assert "Eggs" in item_names
        assert "Bread" in item_names


@pytest.mark.unit
class TestRemoveFromShoppingList:
    """Tests for remove_from_shopping_list function."""

    async def test_remove_existing_item(self, patched_pantry_db, sample_user_id):
        """Test removing an existing item."""
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)

        result = await pantry_service.remove_from_shopping_list(item_name="Milk")

        assert result is True

        # Verify it's gone
        items = await pantry_service.get_shopping_list()
        assert len(items) == 0

    async def test_remove_nonexistent_item(self, patched_pantry_db):
        """Test removing non-existent item returns False."""
        result = await pantry_service.remove_from_shopping_list(item_name="NotExists")

        assert result is False

    async def test_remove_case_insensitive(self, patched_pantry_db, sample_user_id):
        """Test removing is case-insensitive."""
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)

        result = await pantry_service.remove_from_shopping_list(item_name="MILK")

        assert result is True


@pytest.mark.unit
class TestClearShoppingList:
    """Tests for clear_shopping_list function."""

    async def test_clear_empty_list(self, patched_pantry_db):
        """Test clearing empty list returns 0."""
        result = await pantry_service.clear_shopping_list()

        assert result == 0

    async def test_clear_list_with_items(self, patched_pantry_db, sample_user_id):
        """Test clearing list with items."""
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)
        await pantry_service.add_to_shopping_list(item_name="Eggs", user_id=sample_user_id)

        result = await pantry_service.clear_shopping_list()

        assert result == 2

        # Verify list is empty
        items = await pantry_service.get_shopping_list()
        assert len(items) == 0


@pytest.mark.unit
class TestCheckoutShoppingList:
    """Tests for checkout_shopping_list function."""

    async def test_checkout_empty_list(self, patched_pantry_db, sample_user_id):
        """Test checking out empty list."""
        count, items = await pantry_service.checkout_shopping_list(user_id=sample_user_id)

        assert count == 0
        assert items == []

    async def test_checkout_updates_pantry(self, patched_pantry_db, sample_user_id):
        """Test checkout updates pantry inventory."""
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id, quantity=2)
        await pantry_service.add_to_shopping_list(item_name="Eggs", user_id=sample_user_id, quantity=12)

        count, item_names = await pantry_service.checkout_shopping_list(user_id=sample_user_id)

        assert count == 2
        assert "Milk" in item_names
        assert "Eggs" in item_names

        # Verify shopping list is cleared
        shopping_items = await pantry_service.get_shopping_list()
        assert len(shopping_items) == 0

        # Verify pantry items exist with IN_STOCK status
        pantry_items = await pantry_service.get_pantry_items()
        assert len(pantry_items) == 2

        pantry_names = {item["name"]: item for item in pantry_items}
        assert pantry_names["Milk"]["status"] == PantryItemStatus.IN_STOCK
        assert pantry_names["Milk"]["quantity"] == 2
        assert pantry_names["Eggs"]["status"] == PantryItemStatus.IN_STOCK
        assert pantry_names["Eggs"]["quantity"] == 12


@pytest.mark.unit
class TestGetPantryItems:
    """Tests for get_pantry_items function."""

    async def test_get_empty_pantry(self, patched_pantry_db):
        """Test getting empty pantry."""
        result = await pantry_service.get_pantry_items()

        assert result == []

    async def test_get_all_pantry_items(self, patched_pantry_db, sample_user_id):
        """Test getting all pantry items."""
        # Add items via checkout
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)
        await pantry_service.add_to_shopping_list(item_name="Eggs", user_id=sample_user_id)
        await pantry_service.checkout_shopping_list(user_id=sample_user_id)

        result = await pantry_service.get_pantry_items()

        assert len(result) == 2

    async def test_get_pantry_items_by_status(self, patched_pantry_db, sample_user_id):
        """Test filtering pantry items by status."""
        # Add items via checkout
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)
        await pantry_service.checkout_shopping_list(user_id=sample_user_id)

        # Mark one as LOW
        await pantry_service.mark_item_low_or_out(item_name="Eggs", is_out=False)

        in_stock = await pantry_service.get_pantry_items(status=PantryItemStatus.IN_STOCK)
        low_stock = await pantry_service.get_pantry_items(status=PantryItemStatus.LOW)

        assert len(in_stock) == 1
        assert in_stock[0]["name"] == "Milk"

        assert len(low_stock) == 1
        assert low_stock[0]["name"] == "Eggs"


@pytest.mark.unit
class TestMarkItemLowOrOut:
    """Tests for mark_item_low_or_out function."""

    async def test_mark_existing_item_out(self, patched_pantry_db, sample_user_id):
        """Test marking existing item as out."""
        # Create item via checkout
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)
        await pantry_service.checkout_shopping_list(user_id=sample_user_id)

        result = await pantry_service.mark_item_low_or_out(item_name="Milk", is_out=True)

        assert "OUT" in result

        # Verify status updated
        items = await pantry_service.get_pantry_items(status=PantryItemStatus.OUT)
        assert len(items) == 1
        assert items[0]["name"] == "Milk"

    async def test_mark_existing_item_low(self, patched_pantry_db, sample_user_id):
        """Test marking existing item as low."""
        # Create item via checkout
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)
        await pantry_service.checkout_shopping_list(user_id=sample_user_id)

        result = await pantry_service.mark_item_low_or_out(item_name="Milk", is_out=False)

        assert "LOW" in result

    async def test_mark_nonexistent_item_creates_it(self, patched_pantry_db):
        """Test marking non-existent item creates it in pantry."""
        result = await pantry_service.mark_item_low_or_out(item_name="NewItem", is_out=True)

        assert "OUT" in result

        # Verify item was created
        items = await pantry_service.get_pantry_items()
        assert len(items) == 1
        assert items[0]["name"] == "NewItem"
        assert items[0]["status"] == PantryItemStatus.OUT


@pytest.mark.unit
class TestUpdatePantryItemStatus:
    """Tests for update_pantry_item_status function."""

    async def test_update_existing_item(self, patched_pantry_db, sample_user_id):
        """Test updating status of existing item."""
        # Create item via checkout
        await pantry_service.add_to_shopping_list(item_name="Milk", user_id=sample_user_id)
        await pantry_service.checkout_shopping_list(user_id=sample_user_id)

        result = await pantry_service.update_pantry_item_status(
            item_name="Milk",
            status=PantryItemStatus.LOW,
        )

        assert result is not None
        assert result["status"] == PantryItemStatus.LOW

    async def test_update_nonexistent_item(self, patched_pantry_db):
        """Test updating non-existent item returns None."""
        result = await pantry_service.update_pantry_item_status(
            item_name="NotExists",
            status=PantryItemStatus.LOW,
        )

        assert result is None
