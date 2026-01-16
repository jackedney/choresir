# Feature Request: Smart Pantry & Grocery Management

## Problem
Household members constantly struggle with inventory management ("We're out of milk") and fragmented shopping lists. The current system relies on users manually remembering to tell the bot or each other, leading to duplication or missed items.

## Proposed Solution
Add a "Smart Pantry" module that tracks inventory and manages a shared grocery list. The system should allow users to log usage, add items to a list, and "check out" the list when shopping.

## User Stories
*   As a user, I want to say "We need eggs" and have it added to the shared list.
*   As a user, I want to say "I'm at the store" and receive the current shopping list.
*   As a user, I want to say "I bought the list" and have the items moved from the list to the inventory.
*   As a user, I want the bot to remind me to buy milk if it predicts we are out (Future/AI enhancement).

## Technical Implementation

### Schema Changes
New collection `inventory_items`:
*   `name`: text
*   `quantity`: number
*   `status`: select (IN_STOCK, LOW, OUT)
*   `last_restocked`: datetime

New collection `shopping_list`:
*   `item_name`: text
*   `added_by`: relation (users)
*   `added_at`: datetime

### New Tools
*   `tool_inventory_add(item_name: str, quantity: int)`
*   `tool_list_add(item_name: str)`
*   `tool_list_get()`
*   `tool_list_checkout()`: Marks items as bought, updates inventory.

### Agent Behavior
*   When a user mentions running out of something, call `tool_list_add`.
*   When a user mentions shopping, call `tool_list_get`.
