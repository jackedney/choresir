# ADR 008: Gamification & Analytics

**Status:** Accepted  
**Date:** 2026-01-17

## Context

Household chores are inherently boring and lack engagement. While the core chore tracking system is functional, it lacks "stickiness" - there is no social reward mechanism or competitive element to motivate consistent participation. Users log and verify chores, but there's no broader feedback loop showing their contribution relative to others or celebrating their achievements.

We need a system that:

1. Provides visibility into individual and household performance
2. Creates social accountability through public leaderboards
3. Injects dopamine through gamified elements (rankings, titles, emojis)
4. Encourages consistent participation through recognition
5. Maintains the existing simple interaction model

## Decisions

### 1. Weekly Automated Leaderboard

We chose to implement an **automated weekly report** rather than an on-demand-only system.

**Rationale:**

- **Predictable Cadence:** Sunday evening (8pm) creates a weekly ritual and anticipation
- **Passive Engagement:** Users don't need to remember to check; the report comes to them
- **Social Pressure:** Public posting creates healthy competition and accountability
- **Celebration Moment:** End-of-week timing allows for reflection and acknowledgment

**Implementation:**

- Scheduled job using `APScheduler` with `CronTrigger`
- Runs every Sunday at 20:00 (configurable via `WEEKLY_REPORT_HOUR` and `WEEKLY_REPORT_DAY`)
- Sends formatted message to all active users via WhatsApp
- 7-day rolling window (Monday 00:00 to Sunday 20:00)

**Message Format:**

```text
🏆 *Weekly Chore Report*

🥇 *Alice* (12 chores) - _"Carrying the team!"_
🥈 *Bob* (5 chores)
🥉 *Charlie* (1 chore) - _"Room for improvement"_

*Total House Output:* 18 chores
*Most Neglected Chore:* "Clean Bathroom" (Overdue by 5 days)
```text

### 2. On-Demand Personal Stats

We implemented a `/stats` command for individual performance queries.

**Rationale:**

- **User Control:** Allows users to check their standing anytime without waiting for weekly report
- **Privacy Option:** Users can check stats privately without announcing to the group
- **Immediate Feedback:** Satisfies curiosity and provides instant gratification
- **Flexible Periods:** Supports both weekly (7d) and monthly (30d) views

**Triggers:** "stats", "score", "how am I doing", "ranking", "leaderboard"

**Data Displayed:**

- Rank in household (with "Not ranked yet" for new users)
- Chores completed in period
- Pending verifications count
- Overdue chores assigned to user
- Dynamic performance title
- Contextual encouragement/warnings

### 3. Analytics Service Architecture

We chose to create a dedicated `analytics_service` rather than embedding logic in tools or the agent.

**Rationale:**

- **Separation of Concerns:** Business logic separated from presentation and agent tools
- **Reusability:** Service functions can be called from multiple contexts (scheduler, tools, future APIs)
- **Testability:** Pure functions with clear inputs/outputs are easier to test
- **Maintainability:** Analytics logic centralized in one module

**Service Functions:**

- `get_leaderboard(period_days)`: Completion counts per user, sorted descending
- `get_user_statistics(user_id, period_days)`: Individual performance metrics
- `get_completion_rate(period_days)`: On-time vs overdue analysis
- `get_overdue_chores(user_id, limit)`: Overdue chore listing
- `get_household_summary(period_days)`: Overall household metrics

**Design Pattern:**

- All functions are async (consistent with rest of codebase)
- Return structured dictionaries (not formatted strings)
- Formatting happens in presentation layer (tools, scheduler)
- Database queries use filter_query for efficiency

### 4. Dynamic Title System

We implemented context-aware titles that adapt based on performance.

**Rationale:**

- **Positive Reinforcement:** Rewards high performers with encouraging titles
- **Gentle Nudging:** Low performers get mild shame without being harsh
- **Nuance:** Different thresholds avoid one-size-fits-all labeling
- **Fun:** Playful language makes the system feel less serious

**Title Thresholds (User Stats):**

```python
TITLE_THRESHOLD_MACHINE = 10      # "🏆 The Machine"
TITLE_THRESHOLD_CONTRIBUTOR = 5   # "💪 Solid Contributor"
TITLE_THRESHOLD_STARTER = 1       # "👍 Getting Started"
# 0 completions                   # "😴 The Observer"
```python

**Title Logic (Weekly Leaderboard):**

```python
COMPLETIONS_CARRYING_TEAM = 5
COMPLETIONS_NEEDS_IMPROVEMENT = 2

# Rank 1 + 5+ completions → "Carrying the team!"
# Rank 1 + <5 completions → "MVP!"
# Last place + 0 completions → "The Observer"
# Last place + 1-2 completions → "Room for improvement"
# All others → No title
```text

### 5. No Schema Changes

We chose to build analytics entirely on the existing `logs` and `chores` collections.

**Rationale:**

- **Simplicity:** Avoid migration complexity and schema versioning
- **Aggregation on Demand:** Analytics are calculated at query time, not pre-aggregated
- **Flexibility:** Easy to adjust metrics without schema changes
- **Audit Trail:** Existing logs provide complete history for any time period

**Trade-off Accepted:**

- Queries must scan logs for each request (acceptable for current scale)
- No historical snapshots of leaderboards (not required for MVP)
- On-time completion metrics are not yet accurate (deadline history not tracked)

**Performance Optimizations:**

- Database-level filtering with PocketBase `filter_query`
- Optional `limit` parameter for overdue queries
- Efficient user lookup caching within functions
- Logfire spans for observability

### 6. Scheduler Integration

We extended the existing `APScheduler` setup rather than creating a new scheduling system.

**Rationale:**

- **Consistency:** Already using APScheduler for daily reminders and reports
- **Proven:** Library is reliable and well-tested
- **Configuration:** CronTrigger provides flexible scheduling
- **Lifecycle Management:** Integrates cleanly with FastAPI startup/shutdown

**Jobs Registered:**

1. **Overdue Reminders** - Daily at 8am
2. **Daily Report** - Daily at 9pm
3. **Weekly Leaderboard** - Sunday at 8pm
4. **Personal Chore Reminders** - Daily at 8am
5. **Auto-Verification** - Hourly (every hour at minute 0)

**Error Handling:**

- Each job wrapped in try/except
- Individual user failures don't crash the job
- Comprehensive logging with Logfire
- Graceful degradation (continues on errors)

### 7. UX Decisions

#### Emoji Usage

Heavy emoji integration for visual engagement and emotional impact:

- 🏆 Weekly report header
- 🥇🥈🥉 Rank medals (top 3)
- 📊 Stats header
- ⚠️ Warnings for overdue chores
- 💡 Encouragement tips
- Dynamic title emojis (🏆💪👍😴)

#### WhatsApp Formatting

- `*bold*` for headers and emphasis
- `_italic_` for commentary and titles
- Clean line breaks and spacing
- Scannable message structure

#### Period Labels

Smart labeling for common time periods:

- 7 days → "This Week"
- 30 days → "This Month"
- Other → "Last N Days"

#### Grammar & Polish

- Singular/plural handling ("1 day" vs "2 days")
- Contextual messages (encouragement vs warnings)
- Natural language ("Not ranked yet" vs "#None")

### 8. Extension Points (Not Implemented)

**Considered but deferred:**

- **Streaks:** Tracking consecutive weeks of participation
- **Verification Reliability Score:** Percentage of honest verifications
- **Badges/Achievements:** Unlockable icons for milestones
- **Historical Trends:** Graph of performance over time
- **Team Challenges:** Household-wide goals
- **Deadline History:** Tracking original deadlines for on-time metrics

**Rationale for Deferral:**

- MVP feature set sufficient to validate engagement
- Additional features require more complex data tracking
- User feedback needed before investing in advanced features

## Consequences

### Positive

- **Increased Engagement:** Weekly leaderboard creates anticipation and ritual
- **Social Accountability:** Public rankings encourage participation
- **Immediate Feedback:** On-demand stats satisfy curiosity
- **Low Maintenance:** No schema changes, leverages existing data
- **Extensible:** Clear service layer for future enhancements
- **Observable:** Comprehensive logging and error handling

### Negative

- **No Historical Data:** Can't view past leaderboards (only current period)
- **Limited Metrics:** On-time completion rate not yet accurate
- **Query Performance:** Analytics calculated on-demand (may need optimization at scale)
- **No Personalization:** All users see same thresholds and titles

### Neutral

- **Weekly Cadence:** Fixed schedule may not suit all households (configurable)
- **Public Leaderboard:** No private mode (intentional design choice)
- **Text-Only:** No images or charts (WhatsApp limitation)

## Implementation Notes

**Files Modified:**

- `src/services/analytics_service.py` - Core analytics business logic
- `src/agents/tools/analytics_tools.py` - Agent tools and formatting
- `src/core/scheduler.py` - Automated job definitions
- `src/core/config.py` - Configuration constants
- `src/agents/choresir_agent.py` - Agent instructions update

**Configuration:**

```python
# src/core/config.py
WEEKLY_REPORT_HOUR: int = 20  # 8pm Sunday
WEEKLY_REPORT_DAY: int = 6    # Sunday (0=Monday, 6=Sunday)
```

**Key Functions:**

- `analytics_service.get_leaderboard(period_days)` - 7/30/custom day leaderboard
- `analytics_service.get_user_statistics(user_id, period_days)` - Individual stats
- `scheduler.send_weekly_leaderboard()` - Automated Sunday job
- `tool_get_stats(ctx, params)` - Agent tool for user stats

**Testing Strategy:**

- Integration testing via existing workflow tests
- Manual verification of message formatting
- Logfire observability for production monitoring
- Consider adding dedicated analytics unit tests

## Alternatives Considered

### Alternative 1: Daily Leaderboard

**Rejected.** Too frequent; would become noise. Weekly cadence provides better balance.

### Alternative 2: Only On-Demand Stats (No Automated Report)

**Rejected.** Relies on users remembering to check. Misses opportunity for social engagement.

### Alternative 3: Pre-Aggregated Analytics Tables

**Rejected.** Adds schema complexity for marginal performance gain at current scale.

### Alternative 4: External Analytics Service (e.g., Mixpanel, PostHog)

**Rejected.** Overkill for simple household use case. Want to keep data self-contained.

### Alternative 5: Mobile App with Charts/Graphs

**Rejected.** Out of scope. Want to maintain WhatsApp-only interaction model.

## Future Considerations

**If Engagement is High:**

- Implement streaks and verification reliability tracking
- Add historical leaderboard archive
- Create badge/achievement system
- Build household-wide challenge modes

**If Performance Becomes Issue:**

- Add materialized views or summary tables
- Implement caching layer for frequently accessed metrics
- Consider read replicas for analytics queries

**If Customization is Requested:**

- Make title thresholds configurable per household
- Allow users to opt-out of public leaderboard
- Support custom reward messages
- Enable household-specific gamification rules

## Related ADRs

- [ADR 002: Agent Framework](002-agent-framework.md) - Established Pydantic AI agent architecture for tools
- [ADR 007: Operations](007-operations.md) - Defined data schema that analytics queries depend on
