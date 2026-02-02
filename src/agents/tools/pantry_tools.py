"""Pantry and shopping list management tools for the choresir agent."""

import logging

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.domain.pantry import PantryItemStatus
from src.services import pantry_service


logger = logging.getLogger(__name__)


class AddToShoppingList(BaseModel):
    """Parameters for adding an item to the shopping list."""

    item_name: str = Field(description="Name of the item to add (e.g., 'milk', 'eggs')", min_length=1)
    quantity: int | None = Field(default=None, description="Optional quantity to buy")
    notes: str = Field(default="", description="Optional notes (e.g., 'organic', 'large size')")


class RemoveFromShoppingList(BaseModel):
    """Parameters for removing an item from the shopping list."""

    item_name: str = Field(description="Name of the item to remove", min_length=1)


class MarkItemStatus(BaseModel):
    """Parameters for marking a pantry item's status."""

    item_name: str = Field(description="Name of the item", min_length=1)
    is_out: bool = Field(
        default=True,
        description="True if completely out, False if just running low",
    )
    add_to_list: bool = Field(
        default=True,
        description="Whether to automatically add to shopping list",
    )


async def tool_add_to_shopping_list(ctx: RunContext[Deps], params: AddToShoppingList) -> str:
    """
    Add an item to the shared shopping list.

    IMPORTANT: If the item already exists, quantities are accumulated (added together).
    Example: Adding milk x2 when milk x3 is already on the list results in milk x5.

    Use when a user says things like:
    - "We need eggs"
    - "Add milk to the list"
    - "Running out of bread"

    For replacing quantities, use remove_from_shopping_list first, then add.

    Args:
        ctx: Agent runtime context with dependencies
        params: Shopping list item parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_add_to_shopping_list", item=params.item_name):
            # Check if item already exists to provide better feedback
            existing_items = await pantry_service.get_shopping_list()
            existing_item = next(
                (item for item in existing_items if item["item_name"].lower() == params.item_name.lower()),
                None,
            )

            await pantry_service.add_to_shopping_list(
                item_name=params.item_name,
                user_id=ctx.deps.user_id,
                quantity=params.quantity,
                notes=params.notes,
            )

            # Provide clear feedback about what happened
            if existing_item and params.quantity:
                old_qty = existing_item.get("quantity") or 0
                new_qty = old_qty + params.quantity
                return f"Added {params.quantity} more '{params.item_name}' to the shopping list (now x{new_qty} total)."
            if existing_item:
                return f"Updated '{params.item_name}' on the shopping list."
            qty_msg = f" (x{params.quantity})" if params.quantity else ""
            notes_msg = f" - {params.notes}" if params.notes else ""
            return f"Added '{params.item_name}'{qty_msg} to the shopping list{notes_msg}."

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Failed to add to shopping list", extra={"error": str(e)})
        return f"Error: Unable to add item to shopping list. {e!s}"


async def tool_get_shopping_list(_ctx: RunContext[Deps]) -> str:
    """
    Get the current shopping list.

    Use when a user says things like:
    - "What's on the shopping list?"
    - "I'm at the store"
    - "Show me the list"

    Args:
        ctx: Agent runtime context with dependencies

    Returns:
        Formatted shopping list or message if empty
    """
    try:
        with logfire.span("tool_get_shopping_list"):
            items = await pantry_service.get_shopping_list()

            if not items:
                return "The shopping list is empty."

            # Format the list
            lines = ["Shopping List:"]
            for item in items:
                name = item["item_name"]
                qty = item.get("quantity")
                notes = item.get("notes", "")

                line = f"• {name}"
                if qty:
                    line += f" (x{qty})"
                if notes:
                    line += f" - {notes}"
                lines.append(line)

            lines.append(f"\nTotal: {len(items)} item(s)")

            return "\n".join(lines)

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Failed to get shopping list", extra={"error": str(e)})
        return f"Error: Unable to retrieve shopping list. {e!s}"


async def tool_checkout_shopping_list(ctx: RunContext[Deps]) -> str:
    """
    Check out the shopping list after shopping.

    Marks all items as bought, updates the pantry inventory to IN_STOCK,
    and clears the shopping list.

    Use when a user says things like:
    - "I bought the list"
    - "Just finished shopping"
    - "Got everything"

    Args:
        ctx: Agent runtime context with dependencies

    Returns:
        Summary of what was checked out
    """
    try:
        with logfire.span("tool_checkout_shopping_list"):
            count, item_names = await pantry_service.checkout_shopping_list(user_id=ctx.deps.user_id)

            if count == 0:
                return "The shopping list was already empty."

            # Format response - show up to max items inline
            max_inline_items = 5
            items_str = ", ".join(item_names[:max_inline_items])
            if len(item_names) > max_inline_items:
                items_str += f", and {len(item_names) - max_inline_items} more"

            return f"Checked out {count} item(s): {items_str}. Pantry updated."

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Failed to checkout shopping list", extra={"error": str(e)})
        return f"Error: Unable to checkout shopping list. {e!s}"


async def tool_remove_from_shopping_list(_ctx: RunContext[Deps], params: RemoveFromShoppingList) -> str:
    """
    Remove an item from the shopping list.

    Use when a user says things like:
    - "Remove eggs from the list"
    - "We don't need milk anymore"
    - "Take bread off the list"

    Args:
        ctx: Agent runtime context with dependencies
        params: Item to remove

    Returns:
        Success or not found message
    """
    try:
        with logfire.span("tool_remove_from_shopping_list", item=params.item_name):
            removed = await pantry_service.remove_from_shopping_list(item_name=params.item_name)

            if removed:
                return f"Removed '{params.item_name}' from the shopping list."
            return f"'{params.item_name}' was not found on the shopping list."

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Failed to remove from shopping list", extra={"error": str(e)})
        return f"Error: Unable to remove item from shopping list. {e!s}"


async def tool_mark_item_out(ctx: RunContext[Deps], params: MarkItemStatus) -> str:
    """
    Mark a pantry item as low or out of stock.

    Optionally adds it to the shopping list automatically.

    Use when a user says things like:
    - "We're out of milk"
    - "Running low on eggs"
    - "Need more bread"

    Args:
        ctx: Agent runtime context with dependencies
        params: Item status parameters

    Returns:
        Status update message
    """
    try:
        with logfire.span("tool_mark_item_out", item=params.item_name, is_out=params.is_out):
            status_msg = await pantry_service.mark_item_low_or_out(
                item_name=params.item_name,
                is_out=params.is_out,
            )

            # Optionally add to shopping list
            if params.add_to_list:
                await pantry_service.add_to_shopping_list(
                    item_name=params.item_name,
                    user_id=ctx.deps.user_id,
                )
                status_msg += " Added to shopping list."

            return status_msg

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Failed to mark item status", extra={"error": str(e)})
        return f"Error: Unable to update item status. {e!s}"


async def tool_get_pantry_status(_ctx: RunContext[Deps]) -> str:
    """
    Get the current pantry inventory status.

    Shows items that are low or out of stock.

    Use when a user says things like:
    - "What do we need?"
    - "What's running low?"
    - "Check the pantry"

    Args:
        ctx: Agent runtime context with dependencies

    Returns:
        Formatted pantry status
    """
    try:
        with logfire.span("tool_get_pantry_status"):
            # Get items that are low or out
            out_items = await pantry_service.get_pantry_items(status=PantryItemStatus.OUT)
            low_items = await pantry_service.get_pantry_items(status=PantryItemStatus.LOW)

            if not out_items and not low_items:
                return "All pantry items are in stock."

            lines = ["Pantry Status:"]

            if out_items:
                lines.append("\nOut of stock:")
                for item in out_items:
                    lines.append(f"• {item['name']}")

            if low_items:
                lines.append("\nRunning low:")
                for item in low_items:
                    lines.append(f"• {item['name']}")

            return "\n".join(lines)

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Failed to get pantry status", extra={"error": str(e)})
        return f"Error: Unable to retrieve pantry status. {e!s}"


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent."""
    agent.tool(tool_add_to_shopping_list)
    agent.tool(tool_get_shopping_list)
    agent.tool(tool_checkout_shopping_list)
    agent.tool(tool_remove_from_shopping_list)
    agent.tool(tool_mark_item_out)
    agent.tool(tool_get_pantry_status)
