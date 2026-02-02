"""Pantry service for inventory and shopping list management."""

import logging
from datetime import datetime
from typing import Any

from src.core import db_client
from src.core.db_client import sanitize_param
from src.core.logging import span
from src.domain.pantry import PantryItemStatus


logger = logging.getLogger(__name__)


async def add_to_shopping_list(
    *,
    item_name: str,
    user_id: str,
    quantity: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Add an item to the shopping list.

    If the item already exists on the list, quantities are accumulated (added together).
    For example, adding "milk x2" then "milk x3" results in "milk x5".
    This behavior supports multiple household members adding items naturally.

    To replace a quantity instead, remove the item first then re-add it.

    Args:
        item_name: Name of item to add
        user_id: ID of user adding the item
        quantity: Optional quantity to buy (accumulates if item exists)
        notes: Optional notes about the item (replaces existing notes)

    Returns:
        Created or updated shopping list item record
    """
    with span("pantry_service.add_to_shopping_list"):
        # Check if item already exists on shopping list (case-insensitive)
        # Use PocketBase's ~ operator for case-insensitive matching at database level
        existing_item = await db_client.get_first_record(
            collection="shopping_list",
            filter_query=f'item_name ~ "{sanitize_param(item_name)}"',
        )

        if existing_item:
            # Update existing item
            update_data: dict[str, Any] = {"added_by": user_id, "added_at": datetime.now().isoformat()}
            if quantity is not None:
                update_data["quantity"] = (existing_item.get("quantity") or 0) + quantity
            if notes:
                update_data["notes"] = notes

            record = await db_client.update_record(
                collection="shopping_list",
                record_id=existing_item["id"],
                data=update_data,
            )
            logger.info(f"Updated shopping list item: {item_name}")
            return record

        # Create new item
        item_data = {
            "item_name": item_name,
            "added_by": user_id,
            "added_at": datetime.now().isoformat(),
            "quantity": quantity,
            "notes": notes,
        }

        record = await db_client.create_record(collection="shopping_list", data=item_data)
        logger.info(f"Added to shopping list: {item_name}", extra={"user_id": user_id})

        return record


async def get_shopping_list() -> list[dict[str, Any]]:
    """Get the current shopping list.

    Returns:
        List of shopping list item records, sorted by when they were added
    """
    with span("pantry_service.get_shopping_list"):
        records = await db_client.list_records(
            collection="shopping_list",
            sort="+added_at",
        )

        logger.debug(f"Retrieved {len(records)} shopping list items")
        return records


async def remove_from_shopping_list(*, item_name: str) -> bool:
    """Remove an item from the shopping list.

    Args:
        item_name: Name of item to remove (case-insensitive)

    Returns:
        True if item was removed, False if not found
    """
    with span("pantry_service.remove_from_shopping_list"):
        # Find the item (case-insensitive)
        # Use PocketBase's ~ operator for case-insensitive matching at database level
        item = await db_client.get_first_record(
            collection="shopping_list",
            filter_query=f'item_name ~ "{sanitize_param(item_name)}"',
        )

        if item:
            await db_client.delete_record(collection="shopping_list", record_id=item["id"])
            logger.info(f"Removed from shopping list: {item_name}")
            return True

        return False


async def clear_shopping_list() -> int:
    """Clear all items from the shopping list.

    Returns:
        Number of items cleared
    """
    with span("pantry_service.clear_shopping_list"):
        items = await db_client.list_records(collection="shopping_list")
        count = 0

        for item in items:
            await db_client.delete_record(collection="shopping_list", record_id=item["id"])
            count += 1

        logger.info(f"Cleared shopping list: {count} items removed")
        return count


async def checkout_shopping_list(*, user_id: str) -> tuple[int, list[str]]:
    """Check out the shopping list - marks items as bought and updates pantry.

    This moves items from the shopping list to the pantry inventory,
    marking them as IN_STOCK.

    Note: This operation is not atomic. If it fails midway, some items may be
    updated in pantry while still remaining on the shopping list. The error will
    be logged with details about which items were processed. Users should retry
    the checkout operation if it fails.

    Args:
        user_id: ID of user checking out

    Returns:
        Tuple of (number of items checked out, list of item names)

    Raises:
        Exception: If any step of the checkout process fails
    """
    with span("pantry_service.checkout_shopping_list"):
        items = await db_client.list_records(collection="shopping_list")

        if not items:
            return 0, []

        item_names = []
        processed_items = []
        now = datetime.now().isoformat()

        try:
            for item in items:
                item_name = item["item_name"]
                quantity = item.get("quantity") or 1
                item_names.append(item_name)

                # Update or create pantry item
                await _update_pantry_item(
                    item_name=item_name,
                    quantity=quantity,
                    status=PantryItemStatus.IN_STOCK,
                    last_restocked=now,
                )

                # Remove from shopping list
                await db_client.delete_record(collection="shopping_list", record_id=item["id"])

                processed_items.append(item_name)

        except (RuntimeError, KeyError, ConnectionError):
            logger.error(
                "Checkout failed midway for user %s. Successfully processed %d/%d items: %s. "
                "Data may be inconsistent - some items updated in pantry but still on shopping list.",
                user_id,
                len(processed_items),
                len(items),
                processed_items,
                exc_info=True,
            )
            raise

        logger.info(f"Checked out {len(item_names)} items from shopping list (user: {user_id})")
        return len(item_names), item_names


async def _update_pantry_item(
    *,
    item_name: str,
    quantity: int,
    status: PantryItemStatus,
    last_restocked: str,
) -> dict[str, Any]:
    """Update or create a pantry item.

    Args:
        item_name: Name of item
        quantity: Quantity to set
        status: Stock status
        last_restocked: ISO timestamp of when restocked

    Returns:
        Updated or created pantry item record
    """
    # Check if item exists in pantry (case-insensitive)
    # Use PocketBase's ~ operator for case-insensitive matching at database level
    existing_item = await db_client.get_first_record(
        collection="pantry_items",
        filter_query=f'name ~ "{sanitize_param(item_name)}"',
    )

    if existing_item:
        # Update existing pantry item
        update_data = {
            "quantity": (existing_item.get("quantity") or 0) + quantity,
            "status": status,
            "last_restocked": last_restocked,
        }
        return await db_client.update_record(
            collection="pantry_items",
            record_id=existing_item["id"],
            data=update_data,
        )

    # Create new pantry item
    item_data = {
        "name": item_name,
        "quantity": quantity,
        "status": status,
        "last_restocked": last_restocked,
    }
    return await db_client.create_record(collection="pantry_items", data=item_data)


async def get_pantry_items(*, status: PantryItemStatus | None = None) -> list[dict[str, Any]]:
    """Get pantry items with optional status filter.

    Args:
        status: Optional filter by stock status

    Returns:
        List of pantry item records
    """
    with span("pantry_service.get_pantry_items"):
        filter_query = f'status = "{status}"' if status else ""

        records = await db_client.list_records(
            collection="pantry_items",
            filter_query=filter_query,
            sort="+name",
        )

        logger.debug(f"Retrieved {len(records)} pantry items")
        return records


async def update_pantry_item_status(*, item_name: str, status: PantryItemStatus) -> dict[str, Any] | None:
    """Update the status of a pantry item.

    Args:
        item_name: Name of item to update (case-insensitive)
        status: New status

    Returns:
        Updated record or None if not found
    """
    with span("pantry_service.update_pantry_item_status"):
        # Find the item (case-insensitive)
        # Use PocketBase's ~ operator for case-insensitive matching at database level
        item = await db_client.get_first_record(
            collection="pantry_items",
            filter_query=f'name ~ "{sanitize_param(item_name)}"',
        )

        if item:
            record = await db_client.update_record(
                collection="pantry_items",
                record_id=item["id"],
                data={"status": status},
            )
            logger.info(f"Updated pantry item status: {item_name} -> {status}")
            return record

        return None


async def mark_item_low_or_out(*, item_name: str, is_out: bool = False) -> str:
    """Mark a pantry item as low or out of stock, and optionally add to shopping list.

    Args:
        item_name: Name of item
        is_out: If True, mark as OUT and add to shopping list. If False, mark as LOW.

    Returns:
        Status message
    """
    with span("pantry_service.mark_item_low_or_out"):
        status = PantryItemStatus.OUT if is_out else PantryItemStatus.LOW

        # Update pantry item status
        updated = await update_pantry_item_status(item_name=item_name, status=status)

        if not updated:
            # Item doesn't exist in pantry yet - create it
            await db_client.create_record(
                collection="pantry_items",
                data={
                    "name": item_name,
                    "quantity": 0,
                    "status": status,
                    "last_restocked": None,
                },
            )

        return f"Marked '{item_name}' as {status}."
