# Feature Request: Proactive "Smart Nudge" & Bounty System

## Context
Currently, the agent is reactive. It waits for users to ask "What is due?" or for a cron job to say "This is late." This is easy to ignore. To improve the user experience, the agent needs to facilitate *action*, not just reporting.

## User Story
As a user, I want the system to help me get chores done when I'm free, and incentivize me to pick up slack from others.

## Proposed Solution
Shift from "Reminders" to "Opportunities".

### 1. The Smart Nudge
Instead of "Trash is due", say "Hey Alice, the Trash is due tonight. If you do it now, you'll hit a 5-week streak! 🧼"
- **Context Awareness:** If a user just messaged about something else, don't nag them immediately. Wait for a lull.
- **Personalization:** Reference their stats (e.g., streaks, points).

### 2. The "Bounty" Protocol (Robin Hood Upgrade)
If a chore is Overdue > 24 hours, the system should offer it to *others* as a "Bounty".

**Message to Group:**
> 🚨 **Bounty Alert!**
> "Clean Kitchen" was assigned to **Bob**, but it's 24h overdue.
>
> 🏹 **Steal Opportunity:**
> The first person to claim and complete this gets **Double Credit** (and Bob gets a "Slacker" mark).
>
> Reply "I'll do it" to steal this chore!

**UX Benefits:**
- Creates urgency.
- Gamifies "helping out".
- Solves the "Bob never does his chores" problem by letting others profit from his laziness.

## Technical Implementation
- **Logic:** In the periodic check loop, if `due_date < now - 24h`, transition chore status to `OPEN_BOUNTY`.
- **Messaging:** Send a broadcast message to all *other* active members.
- **Handling Claims:** Update `tool_log_chore` to recognize when a user claims a `OPEN_BOUNTY` chore and apply a multiplier to the analytics log (requires adding `weight` or `points` to `chore_logs` or just handling it in the aggregation logic).

## Acceptance Criteria
- [ ] System identifies overdue chores suitable for bounties.
- [ ] "Steal" logic allows a non-assignee to claim the task without permission.
- [ ] Notification explicitly mentions the "Steal" opportunity.
