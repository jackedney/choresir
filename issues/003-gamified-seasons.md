# Feature Request: Gamified Seasons & Leagues

## Problem
Chore completion often feels like a thankless drudgery. "Points" systems lose meaning if they just accumulate forever without a reset or tangible stakes.

## Proposed Solution
Introduce "Seasons" (e.g., monthly) where points reset, and a winner is crowned. Add "Tiers" (Gold, Silver, Bronze) and configurable rewards/punishments.

## User Stories
*   As a user, I want to see "Who won last month?" so I can claim my reward.
*   As a user, I want to know "How many points to beat Alice?" to get motivated.
*   As a user, I want a "Streak Bonus" for doing chores 3 days in a row.

## Technical Implementation

### Schema Changes
New collection `seasons`:
*   `start_date`: datetime
*   `end_date`: datetime
*   `winner`: relation (users)
*   `status`: select (ACTIVE, ARCHIVED)

New collection `season_stats`:
*   `season`: relation (seasons)
*   `user`: relation (users)
*   `points`: number
*   `chores_completed`: number

### New Tools
*   `tool_season_status()`: Returns current standings.
*   `tool_start_season(duration_days: int)`: Archives old season, starts new one.

### Logic Updates
*   Update `tool_log_chore` to add points to the *current* season's stats.
*   Daily cron job to check for season end and announce winner.
