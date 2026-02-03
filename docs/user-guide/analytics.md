# Analytics & Stats

Track your performance, view leaderboards, and monitor household chore completion rates.

## Overview

WhatsApp Home Boss provides analytics at two levels:

**Personal Analytics**
- Your chore completion count
- Your ranking in the household
- Pending verifications
- Overdue chores assigned to you
- Dynamic performance titles

**Household Analytics**
- Weekly leaderboard (top 3 performers)
- Overall completion rates
- Overdue chores across all members
- Weekly automated reports

## Personal Stats

View your individual performance and ranking.

### Viewing Your Stats

```
Stats
My stats
Score
How am I doing
Ranking
Leaderboard
```

**Example output:**
```
📊 *Your Stats (This Week)*

*💪 Solid Contributor*

Rank: #2
Chores Completed: 7
Pending Verification: 2
Overdue: 1

⚠️ You have 1 overdue chore(s)!
```

### Performance Titles

Your stats include a dynamic title based on your performance:

| Completions | Title | Emoji |
|------------|-------|--------|
| 10+ | The Machine | 🏆 |
| 5-9 | Solid Contributor | 💪 |
| 1-4 | Getting Started | 👍 |
| 0 | The Observer | 😴 |

**Example:**
```
You: Stats

Bot: 📊 *Your Stats (This Week)*
    *🏆 The Machine*
    ...
```

### Time Periods

You can view stats for different time periods:

```
Stats this week
Stats this month
Stats for 14 days
```

Default is "this week" (7 days).

## Weekly Leaderboard

Every Sunday evening, all household members receive an automated weekly report.

### What's Included

- **Top 3 performers** with medal rankings (🥇🥈🥉)
- **Your personal ranking** and chore count
- **Total household output** - total chores completed
- **Most neglected chore** - longest overdue task
- **Contextual commentary** - encouraging titles and warnings

### Report Format

**Example weekly report:**
```
🏆 *Weekly Chore Report*

🥇 *Alex* (12 chores) - _"Carrying the team!"_
🥈 *Sam* (8 chores)
🥉 *Jordan* (5 chores)
📊 *You* (3 chores)

*Total House Output:* 28 chores
*Most Neglected Chore:* "Clean bathroom" (Overdue by 5 days)
```

### Viewing Leaderboard Anytime

You don't have to wait for Sunday - check the leaderboard anytime:

```
Leaderboard
Who's winning?
Top performers
```

Shows top 3 performers for the current period.

## Completion Rates

View household-wide completion statistics.

### On-Time vs Overdue

```
Completion rate
On-time rate
How are we doing?
```

**Example output:**
```
📊 Completion Rate (30 days):
Total: 45 chores
On-time: 78%
Overdue: 22%
```

This metric helps the household understand overall chore performance trends.

## Overdue Chores

See which chores are overdue and how long they've been overdue.

### Viewing Overdue Chores

```
Overdue
Overdue chores
What's overdue?
```

**Example output:**
```
⚠️ 3 overdue chore(s):
• 'Clean bathroom' (5 days)
• 'Take out trash' (2 days)
• 'Water plants' (today)
```

### Time Display

- **today** - Due date was today
- **1 day** - Overdue by 1 day
- **X days** - Overdue by X days

This helps prioritize which overdue tasks need immediate attention.

## Understanding Your Stats

### What Affects Your Ranking

Your leaderboard ranking is based on:
- **Completed chores** - Verified completions in the time period
- **Pending verifications** - Awaiting approval (not yet counted)
- **Overdue chores** - Assigned tasks past due date

### How to Improve Your Ranking

1. **Complete your assigned chores** - Primary way to earn points
2. **Get verified promptly** - Pending completions don't count until verified
3. **Avoid overdue tasks** - Overdue chores hurt your standing
4. **Help with others' chores** - Robin Hood Protocol (if overdue)

### Weekly vs Monthly Views

- **This Week (7 days)** - Recent performance, good for tracking momentum
- **This Month (30 days)** - Broader view, less affected by slow periods

Both views use rolling windows - always shows recent activity.

## Automated Reports

The system sends automated reports to keep the household engaged.

### Weekly Report (Sunday 8pm)

- Top 3 performers with rankings
- Your position in the leaderboard
- Total household chore count
- Most neglected chore
- Performance commentary

### Daily Reports (9pm)

- Summary of day's activity
- New completions
- Pending verifications

### Overdue Reminders (8am daily)

- Your overdue chores
- Reminder to complete or request help

## Common Use Cases

### Checking Your Standing

```
Stats
```
(See your rank, completions, and pending verifications)

### Checking Leaderboard

```
Leaderboard
```
(See top 3 performers)

### Identifying Problem Areas

```
Overdue
```
(Find tasks that need attention)

### Understanding Household Performance

```
Completion rate
```
(See on-time vs overdue percentages)

## Best Practices

1. **Check stats regularly** - Stay aware of your performance
2. **Address overdue tasks promptly** - They hurt your ranking
3. **Verify teammates' completions** - Help keep leaderboard accurate
4. **Use weekly report for reflection** - Celebrate wins and identify improvements

## Privacy Note

- **Personal stats** are private to you
- **Leaderboard** is shared with all household members
- **Personal chore stats** are completely separate and never shared

## Related Topics

- [Household Chores](./chores.md) - Managing shared tasks
- [Personal Chores](./personal-chores.md) - Private task tracking
- [Verification System](./verification.md) - How verification works
