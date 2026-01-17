"""Pantry domain models and enums."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PantryItemStatus(StrEnum):
    """Pantry item stock status."""

    IN_STOCK = "IN_STOCK"
    LOW = "LOW"
    OUT = "OUT"


class PantryItem(BaseModel):
    """Pantry item data transfer object."""

    id: str = Field(..., description="Unique item ID from PocketBase")
    name: str = Field(..., description="Item name (e.g., 'Milk', 'Eggs')")
    quantity: int | None = Field(default=None, description="Current quantity")
    status: PantryItemStatus = Field(default=PantryItemStatus.IN_STOCK, description="Stock status")
    last_restocked: datetime | None = Field(default=None, description="When item was last restocked")


class ShoppingListItem(BaseModel):
    """Shopping list item data transfer object."""

    id: str = Field(..., description="Unique item ID from PocketBase")
    item_name: str = Field(..., description="Item name")
    added_by: str = Field(..., description="User ID who added the item")
    added_at: datetime = Field(..., description="When item was added to list")
    quantity: int | None = Field(default=None, description="Quantity to buy")
    notes: str = Field(default="", description="Optional notes (e.g., 'organic only')")
