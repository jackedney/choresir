# ADR 019: Personal Chores System

**Status:** Accepted  
**Date:** 2026-01-19

## Context

While the household chore system effectively manages shared responsibilities and collaborative accountability, users also have **personal goals and habits** they want to track—such as going to the gym, practicing meditation, or maintaining a study schedule. These personal tasks differ from household chores in fundamental ways:

**Privacy Requirements:**

- Personal chores should not appear on the public household leaderboard
- Users may not want to broadcast every personal activity to roommates
- Completion stats should remain private to the individual

**Verification Needs:**

- Some users benefit from external accountability (e.g., workout buddy verification)
- Others prefer self-accountability without involving housemates
- Auto-verification after a grace period prevents indefinite "pending" states

**System Scope:**

- Household chore infrastructure (scheduling, agent framework, database) can be reused
- Personal chores need separate data collections to enforce privacy boundaries
- Agent routing must distinguish between household vs. personal contexts

We needed a privacy-respecting system for personal goal tracking that coexists with the household chore system without creating confusion or violating user privacy expectations.

## Decisions

### 1. Separate Database Collections

We chose to create **distinct database collections** (`personal_chores`, `personal_chore_logs`) rather than extending existing `chores` and `logs` tables with an `is_personal` flag.

**Rationale:**

- **Privacy Enforcement:** Clear separation prevents accidental leakage of personal data into household reports
- **Query Simplicity:** No need to filter on `is_personal` flag in every household query
- **Schema Clarity:** Personal chores have different fields (no `assigned_to`, has `owner_phone`)
- **Future Flexibility:** Easier to apply different access rules or migrate data if needed

#### Schema Design

**`personal_chores` Collection:**

```python
{
    "owner_phone": str,              # E.164 format, owner identifier
    "title": str,                    # e.g., "Go to gym"
    "recurrence": str | None,        # CRON format, interval, or empty for one-time
    "due_date": datetime | None,     # For one-time tasks only
    "accountability_partner_phone": str | None,  # Optional household member
    "status": "ACTIVE" | "ARCHIVED",
    "created_at": datetime
}
```

**`personal_chore_logs` Collection:**

```python
{
    "personal_chore_id": relation,   # Link to personal_chores
    "owner_phone": str,              # E.164 format
    "completed_at": datetime,
    "verification_status": "SELF_VERIFIED" | "PENDING" | "VERIFIED" | "REJECTED",
    "accountability_partner_phone": str | None,
    "partner_feedback": str | None,
    "notes": str | None
}
```

### 2. Privacy-First Design

Personal chores are **invisible to the household system**.

**Implementation:**

- Personal chore logs do NOT appear in weekly leaderboards
- Personal stats are only accessible by the owner
- No notifications sent to the household about personal chore activity
- Accountability partners receive verification requests for specific chores they're assigned to verify, but these are private 1-on-1 interactions, not broadcast to the household

**Exception:** Accountability partners receive verification requests for specific chores they're assigned to verify, but these are private 1-on-1 interactions, not broadcast to the household.

### 3. Agent Routing with `/personal` Prefix

We implemented an **explicit command prefix** to distinguish personal from household chores.

**Rationale:**

- **User Clarity:** Clear signal that this is a different context (`/personal add "Go to gym"`)
- **Namespace Separation:** Prevents ambiguity between "Gym" personal chore and "Clean Gym" household chore
- **Agent Tool Selection:** Agent can route to personal_chore_tools vs. chore_tools based on prefix
- **Discoverability:** Prefix makes the feature self-documenting

**Trigger Patterns:**

- `/personal add [task]` - Create personal chore
- `/personal log [task]` - Log completion
- `/personal list` - View personal chores
- `/personal remove [task]` - Archive personal chore
- `/personal stats` - View personal stats (private)

**Agent Instructions Addition:**

```text
PERSONAL CHORE ROUTING:
- Use personal_chore_tools for any message starting with "/personal"
- Personal chores are PRIVATE to user (no leaderboard, no household visibility)
- Verification requests go only to accountability partner (if set)
- Auto-verify logs after 48 hours if partner hasn't responded
```

### 4. Optional Accountability Partners

We chose a **hybrid accountability model**: self-verified by default, with optional partner verification.

**Rationale:**

- **User Choice:** Some users need external accountability, others find it demotivating
- **Household Integration:** Leverages existing household members as accountability partners
- **Privacy Preserved:** Partner only sees verification requests, not general stats
- **Graceful Degradation:** Auto-verification after 48 hours prevents indefinite pending states

**Verification Flow:**

1. User creates personal chore (optionally specifies accountability partner by name)
2. When user logs completion:
   - **No partner:** Immediately mark `SELF_VERIFIED`
   - **Partner set:** Mark `PENDING`, notify partner via WhatsApp
3. Partner verifies or rejects within 48 hours
4. If no response after 48 hours: Auto-verify (scheduled job)

**Auto-Verification Strategy:**

- Daily scheduled job checks for logs with `status=PENDING` and `completed_at > 48h ago`
- Updates status to `VERIFIED` and logs auto-verification action
- Prevents indefinite "pending" limbo while maintaining accountability incentive

### 5. Reuse Existing Infrastructure

We reused **recurrence parsing logic** and **agent framework** from household chores.

**Shared Components:**

- **Recurrence Parser:** Same CRON/interval parser used for household chores (`src/utils/recurrence_parser.py`)
- **Agent Framework:** Personal chore tools registered with same Pydantic AI agent
- **Scheduler:** APScheduler handles auto-verification job (alongside household reminders)
- **WhatsApp Integration:** Same Twilio message sending service

**New Service Modules:**

- `src/services/personal_chore_service.py` - CRUD operations for personal chores
- `src/services/personal_verification_service.py` - Logging, verification, auto-verify, stats
- `src/agents/tools/personal_chore_tools.py` - Agent tools for personal chore management

### 6. Fuzzy Matching for User Convenience

We implemented **fuzzy string matching** for chore titles to reduce friction.

**Rationale:**

- **WhatsApp UX:** Typing full exact titles on mobile is tedious
- **User Expectations:** Users expect "gym" to match "Go to gym"
- **Error Prevention:** Reduces "chore not found" errors from typos or partial titles

**Implementation:**

```python
def fuzzy_match_personal_chore(
    chores: list[dict],
    search_term: str
) -> dict | None:
    """Case-insensitive substring matching on chore titles."""
    search_lower = search_term.lower()
    for chore in chores:
        if search_lower in chore["title"].lower():
            return chore
    return None
```

**Example:**

- User has personal chore: "Go to gym 3x per week"
- User types: `/personal log gym`
- Fuzzy match finds "Go to gym 3x per week"

### 7. No Leaderboard Integration

Personal chores explicitly do **NOT** contribute to household leaderboards or analytics.

**Rationale:**

- **Privacy Principle:** Personal goals should not be public competition
- **Different Incentive Model:** Personal chores use intrinsic motivation, not social comparison
- **User Expectations:** Users expect "personal" to mean "private"
- **Design Simplicity:** Avoids complex "show personal stats only to me" UX

**Stats Available:**

- Personal stats command shows private stats (completion rate, pending verifications)
- Stats are ONLY visible to the chore owner
- No household-wide aggregation of personal chore data

## Consequences

### Positive

- **Privacy Respected:** Personal goals remain private, preventing social pressure or embarrassment
- **Accountability Options:** Supports both self-directed and partner-verified workflows
- **Reuses Infrastructure:** Leverages existing scheduling, agent, and notification systems
- **Clear Mental Model:** `/personal` prefix makes the feature boundary obvious
- **Prevents Limbo:** 48-hour auto-verification ensures logs don't stay pending forever
- **WhatsApp-Friendly:** Fuzzy matching reduces typing friction on mobile
- **Extensible:** Easy to add badges, streaks, or other personal gamification later

### Negative

- **Schema Duplication:** Separate collections mean some fields are duplicated (e.g., `recurrence` parsing)
- **No Cross-Feature Analytics:** Can't easily compare personal vs. household chore completion rates
- **Partner Notification Noise:** Users may get verification requests from multiple people
- **No Historical Partner Changes:** If partner is changed, old logs still reference the original partner
- **Limited Privacy Controls:** All-or-nothing privacy (can't make specific personal chores public)

### Neutral

- **Two Parallel Systems:** Users must remember `/personal` vs. household chore commands
- **Agent Complexity:** Agent must route between two similar but distinct tool sets
- **Auto-Verification Latency:** 48-hour grace period may feel too long or too short (configurable)

## Implementation Notes

**Files Created:**

- `src/services/personal_chore_service.py` - CRUD operations (create, get, delete, fuzzy_match)
- `src/services/personal_verification_service.py` - Logging, verification, stats, auto-verify job
- `src/agents/tools/personal_chore_tools.py` - 6 agent tools for personal chore management
- Schema additions in `src/core/schema.py` - Two new collections with indexes

**Configuration:**

```python
# Future: Make auto-verification period configurable
PERSONAL_CHORE_AUTO_VERIFY_HOURS = 48
```

**Scheduled Jobs:**

```python
# src/core/scheduler.py
scheduler.add_job(
    func=auto_verify_expired_personal_chores,
    trigger=CronTrigger(hour=0, minute=0),  # Daily at midnight
    id="auto_verify_personal_chores",
    name="Auto-verify expired personal chore logs"
)
```

**Agent Tools:**

1. `tool_create_personal_chore(title, recurrence, accountability_partner_name)`
2. `tool_log_personal_chore(chore_title_fuzzy, notes)`
3. `tool_verify_personal_chore(log_id, approved, feedback)`
4. `tool_get_personal_stats(period_days)`
5. `tool_list_personal_chores(filter_type)`
6. `tool_remove_personal_chore(chore_title_fuzzy)`

**Database Indexes:**

```sql
-- personal_chores
CREATE INDEX idx_personal_owner ON personal_chores (owner_phone)
CREATE INDEX idx_personal_status ON personal_chores (status)

-- personal_chore_logs
CREATE INDEX idx_pcl_chore ON personal_chore_logs (personal_chore_id)
CREATE INDEX idx_pcl_owner ON personal_chore_logs (owner_phone)
CREATE INDEX idx_pcl_verification ON personal_chore_logs (verification_status)
```

**Testing Strategy:**

- Unit tests for personal_chore_service CRUD operations
- Integration tests for verification flow (pending → verified → rejected)
- Auto-verification job testing with mocked time
- Agent tool tests with mock dependencies
- Privacy verification (ensure personal data doesn't leak to household queries)

## Alternatives Considered

### Alternative 1: Use Existing `chores` Table with `is_personal` Flag

**Rejected.**

- Would require filtering every household query to exclude personal chores
- Risk of accidental privacy leaks (forgot to filter in one query → personal data on leaderboard)
- Schema conflicts (household chores have `assigned_to`, personal chores have `owner_phone`)
- Harder to enforce different access rules

### Alternative 2: Always Require Accountability Partner

**Rejected.**

- Too restrictive; many users prefer self-accountability
- Forces users to involve housemates in private goals
- Reduces adoption for users without willing accountability partners

### Alternative 3: Always Self-Verified (No Partner Option)

**Rejected.**

- Removes valuable accountability mechanism for users who need it
- Misses opportunity to create positive peer support dynamics
- Research shows external accountability improves habit formation

### Alternative 4: No Auto-Verification (Indefinite Pending)

**Rejected.**

- Logs would accumulate in "pending" state if partner forgets
- Creates frustrating UX (user did work but can't get credit)
- Penalizes users for partner inattentiveness

### Alternative 5: Personal Chores Contribute to Leaderboard

**Rejected.**

- Violates privacy expectation of "personal" chores
- Incentivizes logging fake personal chores to boost household rank
- Confuses the purpose of household vs. personal systems

### Alternative 6: Separate Bot/App for Personal Chores

**Rejected.**

- Increases user friction (two apps to manage)
- Misses synergy with existing household members as accountability partners
- Duplicates infrastructure (scheduling, WhatsApp integration, database)

## Future Considerations

**If Users Request More Privacy Controls:**

- Allow marking specific personal chores as "shareable" (opt-in to leaderboard)
- Support multiple accountability partners per chore
- Add "anonymous accountability" (partner knows someone needs verification, not who)

**If Auto-Verification Period Needs Tuning:**

- Make `AUTO_VERIFY_HOURS` configurable per user or per chore
- Add reminder to partner before auto-verification kicks in
- Allow users to manually trigger early verification

**If Personal Gamification is Requested:**

- Personal streaks (consecutive days/weeks of completing personal goals)
- Personal badges (unlocked at milestones: 10 completions, 30-day streak, etc.)
- Personal charts/graphs (completion trend over time)
- **Important:** Keep these features isolated from household leaderboard

**If Cross-System Analytics Become Valuable:**

- Add admin-only aggregate stats (household avg personal chores per user)
- Support "total productivity" view (household + personal combined, private to user)
- Correlation analysis (does household chore burden affect personal goal completion?)

## Related ADRs

- [ADR 002: Agent Framework](002-agent-framework.md) - Established Pydantic AI tool architecture
- [ADR 003: Verification Protocol](003-verification.md) - Verification requirements that personal chores also use
- [ADR 007: Operations](007-operations.md) - Defined database schema patterns and onboarding protocol
- [ADR 008: Gamification](008-gamification.md) - Household leaderboard that personal chores intentionally avoid
- [ADR 009: Interactive Verification](009-interactive-verification.md) - Verification flow reused for partner verification

## References

- Implementation PR: [#41 - Add personal chore tracking system](https://github.com/[owner]/whatsapp-home-boss/pull/41)
- Service modules: `src/services/personal_chore_service.py`, `src/services/personal_verification_service.py`
- Agent tools: `src/agents/tools/personal_chore_tools.py`
- Recurrence parser refactor: Extracted shared logic between household and personal chores
