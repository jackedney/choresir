# Feature Request: Gamified Weekly Leaderboards & Stats

## Context
Currently, the system is functional but lacks "stickiness". Users log chores and verify them, but there is no broader social loop or reward mechanism. Household chores are inherently boring; we need to inject dopamine into the process.

## User Story
As a household member, I want to see how my contribution compares to others so that I feel recognized for my hard work (or shamed into helping more).

## Proposed Solution
Implement a **Weekly Sunday Report** and a `/stats` command.

### 1. The Sunday Report (Automated)
Every Sunday at 8:00 PM, the system should post a summary message to the group:

> **🏆 Weekly Chore Report**
>
> 🥇 **MVP:** Alice (12 chores) - _"Carrying the team!"_
> 🥈 **Runner Up:** Bob (5 chores)
> 🥉 **Participant:** Charlie (1 chore) - _"You can do better."_
>
> **Total House Output:** 18 chores
> **Most Neglected Chore:** "Clean Bathroom" (Overdue by 5 days)

**UX Details:**
- Use emojis heavily.
- Assign dynamic titles based on performance (e.g., "The Slacker", "The Machine").
- Calculated from Monday 00:00 to Sunday 20:00.

### 2. On-Demand Stats (`/stats`)
Allow users to query their own standing at any time.

**Input:** `stats` or `score`
**Output:**
> 📊 **Your Stats (This Month)**
> - Chores Completed: 15
> - Verification Reliability: 100%
> - Current Streak: 3 weeks
> - Rank: #1 in House

## Technical Implementation
- **New Tool:** `tool_get_leaderboard` (extends existing analytics).
- **Scheduler:** Use `apscheduler` or a simple cron loop in `main.py` to trigger the Sunday Report.
- **Database:** No schema changes needed; aggregation can be done on `chore_logs`.

## Acceptance Criteria
- [ ] `/stats` command returns accurate user data.
- [ ] Automated job posts a summary message to the WhatsApp group once a week.
- [ ] Messages are formatted with WhatsApp bolding and emojis.
