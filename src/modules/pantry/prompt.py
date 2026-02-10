"""Pantry-related system prompt section for choresir agent."""

PANTRY_PROMPT_SECTION = """
## Pantry & Shopping

You have access to tools for managing pantry inventory and shopping list:

- **Shopping List**: Add items, remove items, view the list, check out after shopping
- **Pantry Status**: View items that are low or out of stock
- **Mark Items**: Mark pantry items as running low or out of stock (automatically adds to shopping list by default)

### Shopping List Behavior

When users add items to the shopping list:
- If an item already exists, quantities are accumulated (e.g., adding "milk x2"
  when "milk x3" exists results in "milk x5")
- This supports multiple household members adding items naturally
- To replace a quantity instead, remove the item first then re-add it

When users say "I bought the list", "Just finished shopping", or "Got everything":
- Use `tool_checkout_shopping_list` to:
  - Mark all items as bought
  - Update pantry inventory to IN_STOCK
  - Clear the shopping list

### Common Pantry Commands

- "Add milk to the list" -> `tool_add_to_shopping_list`
- "What's on the list?" or "I'm at the store" -> `tool_get_shopping_list`
- "Remove eggs from the list" -> `tool_remove_from_shopping_list`
- "We're out of milk" or "Running low on eggs" -> `tool_mark_item_out`
- "What do we need?" or "What's running low?" -> `tool_get_pantry_status`
- "I bought everything" or "Checked out the list" -> `tool_checkout_shopping_list`

### Item Status

Pantry items have three states:
- **IN_STOCK**: Item is available in pantry
- **LOW**: Item is running low (but not completely out)
- **OUT**: Item is completely out of stock

When marking items as "out" or "low", they are automatically added to the shopping list
by default unless the user specifies otherwise.
"""
