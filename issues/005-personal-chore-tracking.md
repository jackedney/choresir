# Feature Request: Personal Chore Tracking with Accountability Partners

## Context
Currently, the system only tracks **household chores** (shared responsibilities). Users have expressed interest in tracking their own **personal tasks** (fitness, work, hobbies, self-care) within the same WhatsApp interface they already use daily, without cluttering the household leaderboard or creating social pressure around private goals.

## User Story
As a household member, I want to track my personal tasks (gym, work deadlines, hobbies) privately so that I can manage all my responsibilities in one place, with optional accountability from someone I trust.

## Proposed Solution
Implement a **Personal Chore System** that operates in parallel to household chores, with complete privacy by default and optional accountability partnerships.

---

## Core Requirements

### 1. Privacy & Isolation
- **Completely private by default**: Only the creator can see their personal chores
- **Not included in household stats**: Personal chores don't affect leaderboard, weekly reports, or house analytics
- **Separate namespace**: Personal chores never interfere with household chore queries
- **No accidental visibility**: Other users cannot see personal chores unless explicitly granted access as accountability partner

### 2. Task Types Supported
Personal chores should support the same flexibility as household chores:
- ✅ **One-time tasks**: "Finish quarterly report" (due date only)
- ✅ **Recurring habits**: "Go to gym" (every 2 days)
- ✅ **Mixed categories**: Work, fitness, hobbies, self-care, projects, etc.
- ✅ **Optional due dates**: Some tasks are aspirational, not deadline-driven

### 3. Verification Options
Users can choose how accountability works per chore:

#### Option A: Self-Verified (Default)
- User says: "Done gym"
- Bot: "✅ Logged 'Go to gym'. Nice work!"
- No external verification needed

#### Option B: Accountability Partner
- User designates a specific household member as accountability partner
- When user claims completion, accountability partner gets notified
- Partner can approve/reject with feedback
- Example flow:
  ```
  User A: "Done gym"
  Bot → User B (DM): "Alice claims she went to the gym. Verify?"
  User B: "Approve"
  Bot → User A: "✅ Bob verified your gym session!"
  ```

### 4. Complete Separation from Household System
- **No conversion mechanism**: Personal chores stay personal. To make something household, delete personal chore and recreate as household chore
- **No swaps**: Cannot trade personal chores for household chores
- **Separate queries**: `/personal stats` vs `/stats` for household

---

## Slash Commands

### Creating Personal Chores
```
/personal add <task> [recurrence] [accountability:@user]

Examples:
- /personal add gym every 2 days
- /personal add finish report by Friday
- /personal add meditate every morning accountability:@Bob
- /personal add practice guitar
```

### Managing Personal Chores
```
/personal list                     # Show all my personal chores
/personal list pending             # Show incomplete tasks
/personal list overdue             # Show overdue tasks
/personal done <task>              # Mark task complete
/personal remove <task>            # Delete a personal chore
/personal stats                    # Show my personal stats only
/personal stats @Bob               # View Bob's stats (only if you're his accountability partner)
```

### Accountability Partner Commands
```
/personal verify <task> for @User  # Verify someone's personal chore (if you're their partner)
/personal reject <task> for @User  # Reject verification with reason
```

---

## Technical Implementation

### Database Schema Changes

#### New Collection: `personal_chores`
```python
{
  "id": "pc_xyz",
  "owner_phone": "+1234567890",
  "title": "Go to gym",
  "recurrence": "every 2 days",  # Optional
  "due_date": "2026-01-20",      # Optional
  "accountability_partner_phone": None,  # Optional
  "created_at": "2026-01-15T10:00:00Z",
  "status": "ACTIVE"
}
```

#### New Collection: `personal_chore_logs`
```python
{
  "id": "pcl_abc",
  "personal_chore_id": "pc_xyz",
  "owner_phone": "+1234567890",
  "completed_at": "2026-01-18T08:00:00Z",
  "verification_status": "SELF_VERIFIED",  # or "PENDING", "VERIFIED", "REJECTED"
  "accountability_partner_phone": None,    # Optional
  "partner_feedback": None,                # Optional
  "notes": "Early morning session"
}
```

### New Agent Tools

#### `tool_create_personal_chore`
```python
class CreatePersonalChore(BaseModel):
    title: str
    recurrence: str | None = None
    due_date: str | None = None
    accountability_partner_phone: str | None = None
```

#### `tool_log_personal_chore`
```python
class LogPersonalChore(BaseModel):
    chore_title_fuzzy: str
    notes: str | None = None
    request_verification: bool = False  # If False, auto-self-verify
```

#### `tool_verify_personal_chore`
```python
class VerifyPersonalChore(BaseModel):
    log_id: str
    decision: Literal['APPROVE', 'REJECT']
    feedback: str | None = None
```

#### `tool_get_personal_stats`
```python
class GetPersonalStats(BaseModel):
    target_user_phone: str  # Can only query self or accountability partners
    time_range: Literal['WEEK', 'MONTH', 'ALL_TIME']
```

### Services Layer
- **New Service**: `personal_chore_service.py`
  - `create_personal_chore()`
  - `log_personal_chore()`
  - `get_personal_chores_for_user()`
  - `check_accountability_partner_access()`

- **New Service**: `personal_verification_service.py`
  - `notify_accountability_partner()`
  - `verify_personal_chore()`
  - `calculate_personal_stats()`

### Agent Context Updates
The agent needs to understand when commands are personal vs household:
- Parse `/personal` prefix to route to personal tools
- Maintain separate context for personal chores in conversation history
- Prevent accidental leakage of personal chore data in group messages

---

## User Experience Flow

### Example 1: Self-Verified Personal Chore
```
User: /personal add meditate every morning
Bot: ✅ Created personal chore "Meditate" (daily). I'll remind you each morning.

[Next morning]
Bot (DM): 🧘 Reminder: Time to meditate

User: Done meditate
Bot: ✅ Logged "Meditate". Keep the streak going!

User: /personal stats
Bot: 📊 Your Personal Stats (This Week)
     - Meditate: 5/7 days (71% completion)
     - Current Streak: 3 days
```

### Example 2: Accountability Partner Chore
```
User A: /personal add gym every 2 days accountability:@Bob
Bot: ✅ Created "Gym" with Bob as your accountability partner.

[2 days later]
User A: Done gym
Bot → Bob (DM): 💪 Alice claims she went to the gym. Verify?
                [Approve] [Reject]

Bob: Approve
Bot → Alice: ✅ Bob verified your gym session! Keep it up.

Bob: /personal stats @Alice
Bot → Bob: 📊 Alice's Personal Stats (You're her accountability partner)
           - Gym: 8/10 sessions this month (80%)
           - Current Streak: 4 sessions
```

### Example 3: Privacy in Group Chat
```
[Group Chat]
User A: Done gym
Bot (DM to A only): ✅ Logged "Gym" (personal chore). Bob will verify.

User B: What gym?
[Bot does not respond - personal chores are invisible in group chat]
```

---

## Edge Cases & Considerations

### 1. Accountability Partner Permissions
- **Q:** What if user specifies non-existent user as accountability partner?
- **A:** Bot should validate and respond: "User @Charlie is not in this household. Please choose someone from your house."

### 2. Overlapping Names
- **Q:** What if personal chore has same name as household chore?
- **A:** Use namespace prefixes internally (`household:dishes` vs `personal:dishes`). User says "done dishes" → bot asks: "Did you mean household dishes or your personal dishes?"

### 3. Reminders
- **Q:** Should personal chores trigger reminders?
- **A:** Yes, but only in DMs, never in group chat.

### 4. Accountability Partner Leaves House
- **Q:** What if accountability partner leaves the household?
- **A:** Auto-convert affected personal chores to self-verified, notify owner: "Bob left the house. 'Gym' is now self-verified."

### 5. Data Privacy
- **Q:** Can admins see personal chores?
- **A:** No. Not even admins. Personal chores are end-to-end private unless accountability partner is assigned.

---

## Acceptance Criteria

### Core Functionality
- [ ] Users can create personal chores with `/personal add`
- [ ] Personal chores support one-time and recurring patterns
- [ ] Personal chores can be self-verified or partner-verified
- [ ] Self-verified chores auto-complete on "done" claim
- [ ] Accountability partners receive DM notifications for verification
- [ ] Partners can approve/reject with feedback

### Privacy & Isolation
- [ ] Personal chores never appear in household leaderboard
- [ ] Personal chores never appear in `/stats` (household stats)
- [ ] Personal chores are invisible to other users (except accountability partner)
- [ ] Personal chore notifications only sent via DM, never group chat

### Commands
- [ ] `/personal list` shows all user's personal chores
- [ ] `/personal done <task>` logs completion
- [ ] `/personal stats` shows personal analytics
- [ ] `/personal remove <task>` deletes chore

### Edge Cases
- [ ] Bot validates accountability partner is in household
- [ ] Bot handles name collision between personal/household chores
- [ ] Bot auto-converts partner-verified to self-verified if partner leaves
- [ ] Bot prevents unauthorized access to other users' personal chores

---

## Future Enhancements (Out of Scope for v1)
- **Habit Streaks**: Visual streak tracking (e.g., "🔥 7 day streak!")
- **Personal Goals**: Set monthly targets (e.g., "Gym 20 times this month")
- **Categories**: Tag personal chores (fitness, work, hobbies)
- **Export**: Download personal chore history as CSV
- **Multiple Partners**: Assign multiple accountability partners per chore

---

## Technical Notes for Implementers

### Priority: Medium-High
This feature extends the core value prop (task management) without increasing complexity for users who don't need it. The `/personal` namespace keeps it completely opt-in.

### Estimated Complexity: Medium
- **Database**: 2 new collections (straightforward)
- **Agent Tools**: 4 new tools (similar to existing household tools)
- **Services**: 2 new services (can reuse patterns from verification_service)
- **Privacy Logic**: Moderate complexity (need to filter all queries by owner_phone)

### Implementation Order
1. Database schema + migrations
2. `personal_chore_service.py` (CRUD operations)
3. Agent tools for creating/logging personal chores (self-verified only)
4. `/personal stats` command
5. Accountability partner system (verification flow)
6. DM notification routing for privacy

### Testing Priorities
- **Privacy**: Ensure no data leaks between users
- **Accountability Flow**: Partner notification → verification → feedback loop
- **Name Collision**: Personal vs household chore disambiguation
- **Partner Removal**: Graceful handling when accountability partner leaves

---

## Related Issues
- `001-gamified-leaderboards.md` (explicitly excludes personal chores from leaderboard)
- `003-gamified-seasons.md` (personal chores could have separate season tracking in future)

---

## Open Questions
1. Should personal chores have point values (even if not shared publicly)?
2. Should there be a separate personal leaderboard (just for motivation)?
3. Should users be able to share specific personal achievements voluntarily? (e.g., "Share my 30-day gym streak to the group")

---

**Status**: Ready for Implementation
**Priority**: Medium-High
**Estimated LOE**: 3-5 days for full implementation + testing
