# Pantry & Shopping

The pantry and shopping features help your household coordinate grocery shopping and track inventory status.

## Overview

The system includes:
- **Shopping list** - Shared list of items to buy
- **Pantry status** - Track what's low or out of stock
- **Auto-checkout** - Mark all items as bought and update inventory
- **Smart tracking** - Optional auto-add to shopping list when marking items out

## Shopping List

The shopping list is shared across all household members. Anyone can add or remove items.

### Adding Items to the List

Use natural language to add items.

```
Add {item} to the list
We need {item}
Add {item} to shopping list
```

**Examples:**
```
Add milk to the list
We need eggs
Add bread to shopping list
```

### Adding Quantities

Specify how many of an item you need:

```
Add {quantity} {item} to the list
```

**Examples:**
```
Add 6 eggs to the list
Add 2 cartons of milk to the list
Add 3 onions to the list
```

### Adding Notes

Include details like brand, size, or preferences:

```
Add {item} to the list - {notes}
```

**Examples:**
```
Add milk to the list - organic, whole
Add eggs to the list - large, free range
Add coffee to the list - dark roast, whole bean
```

### Viewing the Shopping List

Check what items are on the list:

```
What's on the shopping list?
Show me the list
Shopping list
I'm at the store
```

**Example output:**
```
Shopping List:
• Milk (x2) - organic, whole
• Eggs (x1) - large, free range
• Bread
• Coffee - dark roast, whole bean

Total: 4 item(s)
```

### Removing Items from the List

If you no longer need an item, remove it:

```
Remove {item} from the list
Take {item} off the list
We don't need {item} anymore
```

**Examples:**
```
Remove milk from the list
Take eggs off the list
We don't need bread anymore
```

### Quantity Accumulation

If you add an item that's already on the list, quantities are added together.

**Example:**
```
You: Add 3 eggs to the list
Bot: Added 'eggs' to the shopping list (x3).

You: Add 6 eggs to the list
Bot: Added 6 more 'eggs' to the shopping list (now x9 total).
```

To replace a quantity, remove the item first, then add the new quantity.

## Checkout After Shopping

When you've completed the shopping trip, checkout to update inventory and clear the list.

### Checking Out

```
I bought the list
Just finished shopping
Got everything
Checkout shopping list
```

**What happens:**
1. All items on the shopping list are marked as bought
2. Items are added to pantry inventory (in stock)
3. Shopping list is cleared
4. Bot confirms what was checked out

**Example output:**
```
Checked out 4 item(s): Milk, Eggs, Bread, Coffee. Pantry updated.
```

## Pantry Status

Track which items are running low or out of stock.

### Viewing Pantry Status

```
What do we need?
What's running low?
Check the pantry
Pantry status
```

**Example output:**
```
Pantry Status:

Out of stock:
• Milk
• Eggs

Running low:
• Bread
• Butter
```

This helps you know what to add to the shopping list.

## Marking Items Out of Stock

When you notice an item is running out, mark it as out.

### Marking as Out

```
We're out of {item}
Out of {item}
Need {item}
```

**Examples:**
```
We're out of milk
Out of eggs
Need bread
```

### Auto-Add to Shopping List

By default, when you mark an item out, it's automatically added to the shopping list.

**Example:**
```
You: We're out of milk

Bot: Marked 'milk' as out of stock. Added to shopping list.
```

### Marking as Low (Not Out)

If an item is running low but not completely out:

```
Running low on {item}
Almost out of {item}
```

**Example:**
```
You: Running low on bread

Bot: Marked 'bread' as running low. Added to shopping list.
```

## Common Workflows

### Pre-Store Checklist

Before going to the store:

1. **Check the list:** "What's on the shopping list?"
2. **Check pantry status:** "What do we need?"
3. **Add any missing items:** "Add [item] to the list"

### At the Store

1. **Review the list:** "Show me the list"
2. **Mark off items as you shop:** (mental note or separate list)
3. **Checkout when done:** "I bought the list"

### Post-Store

1. **Verify checkout:** Bot confirms what was bought
2. **Put items away:** Organize your pantry
3. **Mark new shortages:** If you notice anything else running low

## Common Error Messages

### "'{item}' was not found on the shopping list"

**Cause:** The item you're trying to remove isn't on the list.

**Solutions:**
1. Check the current list with "What's on the shopping list?"
2. Use the exact item name
3. Don't worry about removing items you didn't add

### "The shopping list was already empty"

**Cause:** You tried to checkout but the list is empty.

**Solutions:**
1. Add items to the list before checking out
2. Use this command after completing shopping

## Best Practices

1. **Add items as you notice need** - Don't wait until you're at the store
2. **Be specific with notes** - Include brands, sizes, or preferences
3. **Check the list before shopping** - Avoid missing items
4. **Checkout promptly** - Clear the list after shopping
5. **Communicate with household** - Let others know if you're doing the shopping

## Shopping Coordination Tips

### Before You Shop

```
What's on the shopping list?
What do we need?
Add coffee to the list - dark roast, whole bean
```

### While at the Store

```
Show me the list
```
(Review items as you shop)

### After Shopping

```
I bought the list
```
(Bot confirms what was purchased)

### When You Notice Need

```
We're out of milk
Running low on bread
```
(Items are automatically added to list)

## Related Topics

- [Household Chores](./chores.md) - Managing shared tasks
- [Getting Started](./onboarding.md) - Setting up your account
