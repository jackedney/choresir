# Household Chores

Household chores are shared responsibilities that all members can complete and track. They appear on the weekly leaderboard and require peer verification.

## Overview

Household chores are:
- Visible to all household members
- Tracked on the weekly leaderboard
- Require verification from another member
- Can be assigned to specific people or left unassigned
- Support recurring schedules (every X days, weekly, etc.)

## Creating a New Chore

Anyone can create new household chores. Use natural language to specify the chore and how often it needs to be done.

### Basic Format

```
Create chore "{title}" {recurrence}
```

**Examples:**
```
Create chore "Take out trash" every 3 days
Create chore "Clean bathroom" every Friday
Create chore "Water plants" every Monday
```

### Adding Assignees

You can assign a chore to a specific member by including their name or phone number.

```
Create chore "{title}" {recurrence} assigned to {name}
```

**Example:**
```
Create chore "Feed the cat" every morning assigned to Alex
```

If not specified, the chore is unassigned and any member can claim it.

### Adding Descriptions

Include additional details about the chore:

```
Create chore "{title}" {recurrence} - {description}
```

**Example:**
```
Create chore "Clean kitchen" every Friday - Wipe counters, clean sink, take out trash
```

### Supported Recurrence Patterns

- `every X days` - Repeat every N days (e.g., "every 3 days")
- `every {day}` - Repeat on specific day (e.g., "every Friday", "every Monday")
- `every morning/evening` - Daily at general time
- CRON format - For complex schedules (advanced)

## Logging Chore Completions

When you complete a household chore, log it so you earn credit.

### Basic Format

```
Done {chore_name}
```

**Examples:**
```
Done dishes
Done take out trash
Done clean bathroom
```

### Adding Notes

Include details about how you completed the chore:

```
Done {chore_name} - {notes}
```

**Example:**
```
Done dishes - Loaded dishwasher and ran it
```

### What Happens Next

1. The bot marks the chore as "pending verification"
2. Another household member must review and approve your completion
3. Once approved, the chore is marked complete and you earn points

## Viewing Chore Status

Check the status of your chores or another member's chores.

### Your Chores

```
Status
My status
```

Shows:
- Todo chores (upcoming)
- Pending verifications (awaiting approval)
- Completed chores

### Another Member's Chores

```
Status for {name}
```

**Example:**
```
Status for Alex
```

## Verification System

Household chores require peer verification to ensure accountability.

### Why Verification?

- Prevents false claims of completing chores
- Encourages household communication
- Ensures quality standards
- Builds trust through transparency

### How Verification Works

1. **You complete a chore** - Send "Done {chore_name}"
2. **Another member reviews** - They verify you actually did it
3. **Points awarded** - Once verified, you earn points for the leaderboard

### Verifying a Chore

When someone logs a completion, you'll receive a verification request. To approve:

```
Approve {log_id}
```

To reject:

```
Reject {log_id} - {reason}
```

**Note:** You cannot verify your own chore completions.

For more details, see [Verification System](./verification.md).

## Robin Hood Protocol (Helping with Others' Chores)

The Robin Hood Protocol allows you to complete another member's assigned chore when they're unable to.

### Rules

- Any member can take over another's chore before deadline
- Original assignee gets credit if completed on-time
- Person who actually completes it gets credit if overdue
- Weekly limit: 3 takeovers per person

### How It Works

When you log a completion for someone else's chore, the system automatically handles the takeover logic.

**Example:**
```
Done dishes
```

If "dishes" was assigned to Alex but you completed it, the system:
- Tracks it as a Robin Hood swap
- Awards points to Alex if on-time
- Awards points to you if overdue

## Common Error Messages

### "No household chore found matching '{chore_name}'"

**Cause:** The chore name doesn't match any existing household chore.

**Solutions:**
1. Check the spelling and exact chore name
2. Use a partial match (e.g., "dish" instead of "dishes")
3. Create the chore if it doesn't exist

### "Chore '{chore_name}' is in state '{state}' and cannot be logged right now"

**Cause:** The chore is already completed, verified, or in another state.

**Solutions:**
1. Wait for the chore to reset to TODO state
2. Check the current status with "Status"

### "You cannot verify your own chore claim"

**Cause:** You tried to approve your own completion.

**Solutions:**
1. Ask another household member to verify
2. Verification requires peer review

## Best Practices

1. **Use consistent chore names** - Helps avoid confusion when logging
2. **Be specific with notes** - Helps verifiers understand what was done
3. **Verify promptly** - Help teammates by reviewing quickly
4. **Check status regularly** - Stay on top of your responsibilities
5. **Communicate** - Let assignees know if you're doing their chore

## Related Topics

- [Verification System](./verification.md) - Detailed verification guide
- [Analytics & Stats](./analytics.md) - View performance and leaderboards
- [Personal Chores](./personal-chores.md) - Private task tracking
