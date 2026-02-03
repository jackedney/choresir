# Personal Chores

Personal chores are private individual tasks that only you can see. They're perfect for tracking personal goals, habits, or one-time tasks you want to keep private.

## Overview

Personal chores are:
- **Completely private** - Only you can see them
- **Optional verification** - Can be self-verified or have an accountability partner
- **Excluded from leaderboard** - Don't appear in household rankings
- **Flexible scheduling** - Support recurring patterns or one-time tasks

## Creating Personal Chores

Use the `/personal` prefix to create private tasks.

### Basic Format

```
/personal add "{title}"
```

**Examples:**
```
/personal add "Go to gym"
/personal add "Read for 30 minutes"
/personal add "Meditate"
```

### Adding Recurrence

Make your personal chore recurring:

```
/personal add "{title}" every {pattern}
```

**Examples:**
```
/personal add "Go to gym" every Monday
/personal add "Read for 30 minutes" every evening
/personal add "Meditate" every morning
```

**Supported patterns:**
- `every X days` - Repeat every N days
- `every {day}` - Repeat on specific day
- `every morning/evening` - Daily at general time
- `by {day}` - One-time task due by specific day

### One-Time Tasks

For tasks that only need to be done once:

```
/personal add "{task}" by {deadline}
```

**Example:**
```
/personal add "Call dentist" by Friday
```

## Accountability Partners

You can optionally assign an accountability partner to verify your personal chore completions.

### Setting a Partner

```
/personal add "{title}" partner: {name}
```

**Example:**
```
/personal add "Go to gym" every morning partner: Alex
```

### How Partners Work

- Partner can see your verification requests
- Partner approves or rejects your completions
- Partner CANNOT see your stats or chore list
- You can still self-verify if no partner responds

**Important:** Your accountability partner can only verify completions - they cannot view your personal chore list or stats. This maintains privacy while providing accountability.

### Removing a Partner

To stop using a partner, remove the chore and recreate it without the partner parameter.

## Logging Personal Chore Completions

When you complete a personal chore, log it to track your progress.

### Basic Format

```
/personal done {chore_name}
```

**Examples:**
```
/personal done gym
/personal done reading
/personal done meditation
```

### Adding Notes

Include details about your completion:

```
/personal done {chore_name} - {notes}
```

**Example:**
```
/personal done gym - Completed full workout, 45 minutes
```

### What Happens Next

**If you have no accountability partner:**
- Chore is marked complete immediately
- You earn credit in your personal stats

**If you have a partner:**
- Chore is marked "pending verification"
- Partner receives notification to verify
- Once verified, chore is complete

### Self-Verification

If your partner doesn't respond within 48 hours, the system automatically approves your completion with note:
- "Auto-verified (partner did not respond within 48 hours)"

This prevents your tasks from getting stuck while maintaining accountability.

## Viewing Personal Chores

See all your active personal tasks.

```
/personal list
```

Shows:
- Active personal chores
- Recurrence patterns (if any)
- Due information for one-time tasks

**Example output:**
```
📝 Your Personal Chores:

• Go to gym (every morning)
• Read for 30 minutes (every evening)
• Call dentist (by Friday - one-time)
```

## Viewing Personal Stats

Track your personal chore performance.

```
/personal stats
```

Shows:
- Total active personal chores
- Completions in current period
- Pending verifications
- Completion rate percentage

**Example output:**
```
📊 Your Personal Stats (This Week)

Active Chores: 3
Completions: 12
Pending Verification: 1
Completion Rate: 92%
```

## Removing Personal Chores

When you no longer want to track a personal chore, remove it.

```
/personal remove {chore_name}
```

**Example:**
```
/personal remove "Call dentist"
```

This archives the chore - it won't appear in your active list but is preserved in your history.

## Personal Chores vs Household Chores

The system manages two separate chore systems:

| Feature | Household Chores | Personal Chores |
|----------|-----------------|-----------------|
| Visibility | All members see | Only you see |
| Leaderboard | Included | Excluded |
| Verification | Required from another member | Self or optional partner |
| Purpose | Shared responsibilities | Private goals |
| Commands | "Done {chore}" | "/personal done {chore}" |

## Name Collision Handling

If you have both a household chore and personal chore with similar names, the bot will ask you to clarify.

**Example:**
```
You: Done gym

Bot: I found both a household chore 'Gym' and your personal chore 'Gym'.
      Which one did you complete? Reply 'household' or 'personal'.

You: personal

Bot: ✅ Logged 'Gym'. Nice work!
```

This prevents logging the wrong chore accidentally.

## Common Error Messages

### "No personal chore found matching '{chore_name}'"

**Cause:** The chore name doesn't match any of your personal chores.

**Solutions:**
1. Check your personal chore list with `/personal list`
2. Use exact chore name or close match
3. Create the chore if it doesn't exist

### "You cannot be your own accountability partner"

**Cause:** You tried to set yourself as your own accountability partner.

**Solutions:**
1. Choose a different household member as partner
2. Leave the partner field empty for self-verification

### "User '{name}' not found in household"

**Cause:** The accountability partner name doesn't match any household member.

**Solutions:**
1. Check the exact name spelling
2. Use the name as it appears in the household
3. Leave the partner field empty if unsure

## Best Practices

1. **Start with self-verification** - Add accountability partners gradually
2. **Choose trusted partners** - Pick someone who will actually review
3. **Use descriptive names** - Helps with fuzzy matching
4. **Review your list regularly** - Use `/personal list` to stay organized
5. **Set realistic schedules** - Avoid setting yourself up for failure

## Common Use Cases

### Daily Habits

```
/personal add "Meditate" every morning
/personal add "Journal" every evening
```

### Fitness Goals

```
/personal add "Go to gym" every Monday, Wednesday, Friday
/personal add "Run 5k" every Sunday
```

### One-Time Tasks

```
/personal add "Call dentist" by Friday
/personal add "Renew car insurance" by end of month
```

### Learning Goals

```
/personal add "Study Spanish" every evening
/personal add "Practice guitar" every Saturday
```

## Related Topics

- [Household Chores](./chores.md) - Shared task management
- [Analytics & Stats](./analytics.md) - Performance tracking
- [Verification System](./verification.md) - How verification works
