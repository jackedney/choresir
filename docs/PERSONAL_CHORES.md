# Personal Chore System

## Overview

The personal chore system allows household members to track their own individual tasks privately while using the same WhatsApp interface. Personal chores are completely isolated from household chores, providing a privacy-first approach to personal task management.

## Key Features

### 🔒 Privacy & Isolation
- **Completely private by default**: Only the creator can see their personal chores
- **Separate from household analytics**: Personal chores don't affect the household leaderboard or reports
- **DM-only notifications**: All personal chore reminders and feedback sent via direct message
- **No accidental visibility**: Other users cannot see personal chores unless explicitly granted access as accountability partner

### 🤝 Accountability Partner System
- **Optional verification**: Choose self-verified or partner-verified per chore
- **Flexible partnerships**: Assign any active household member as your accountability partner
- **48-hour timeout**: Pending verifications auto-approve after 48 hours
- **Graceful handling**: Auto-converts to self-verified if partner leaves household

### 📅 Flexible Scheduling
- **Recurring habits**: "every 2 days", "every morning", "every Monday"
- **One-time tasks**: "by Friday", "finish report"
- **Mixed categories**: Work, fitness, hobbies, self-care, projects
- **Optional due dates**: Some tasks are aspirational, not deadline-driven

## Commands

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
/personal list                     # Show all your personal chores
/personal done <task>              # Log completion
/personal stats [period_days]      # View your personal statistics (default: 30 days)
/personal remove <task>            # Delete a personal chore
```

### Accountability Partner Commands
```
/personal verify <log_id> approve [feedback]   # Verify someone's chore
/personal verify <log_id> reject [feedback]    # Reject verification
```

## Architecture

### Database Collections

#### `personal_chores`
Stores personal chore definitions:
```python
{
  "id": "pc_xyz",
  "owner_phone": "+1234567890",
  "title": "Go to gym",
  "recurrence": "every 2 days",
  "accountability_partner_phone": None,  # Optional
  "created_at": "2026-01-18T10:00:00Z",
  "status": "ACTIVE"  # or "ARCHIVED"
}
```

#### `personal_chore_logs`
Stores completion logs with verification status:
```python
{
  "id": "pcl_abc",
  "personal_chore_id": "pc_xyz",
  "owner_phone": "+1234567890",
  "completed_at": "2026-01-18T08:00:00Z",
  "verification_status": "SELF_VERIFIED",  # or "PENDING", "VERIFIED", "REJECTED"
  "accountability_partner_phone": None,
  "partner_feedback": None,
  "notes": "Early morning session"
}
```

### Services

#### `personal_chore_service.py`
CRUD operations for personal chores:
- `create_personal_chore()`: Creates new personal chore
- `get_personal_chores()`: Lists chores filtered by owner
- `get_personal_chore_by_id()`: Retrieves specific chore with ownership check
- `delete_personal_chore()`: Archives chore (ownership enforced)
- `fuzzy_match_personal_chore()`: Matches chore names for "done" commands

#### `personal_verification_service.py`
Verification flow and statistics:
- `log_personal_chore()`: Logs completion with ownership validation
- `verify_personal_chore()`: Approves/rejects with partner validation
- `get_pending_partner_verifications()`: Lists pending verifications for partner
- `auto_verify_expired_logs()`: Auto-verifies logs older than 48 hours
- `get_personal_stats()`: Calculates personal analytics

### Agent Tools

#### `tool_create_personal_chore`
Creates a new personal chore with optional accountability partner.
```python
CreatePersonalChore(
    title="Go to gym",
    recurrence="every 2 days",
    accountability_partner_name="Bob"  # Optional
)
```

#### `tool_log_personal_chore`
Logs completion of a personal chore (fuzzy matching supported).
```python
LogPersonalChore(
    chore_title_fuzzy="gym",
    notes="Great session today"  # Optional
)
```

#### `tool_verify_personal_chore`
Verifies someone's personal chore completion (accountability partner only).
```python
VerifyPersonalChore(
    log_id="pcl_abc",
    approved=True,
    feedback="Keep it up!"  # Optional
)
```

#### `tool_get_personal_stats`
Retrieves personal chore statistics.
```python
GetPersonalStats(
    period_days=30  # Default: 30 days
)
```

#### `tool_list_personal_chores`
Lists all active personal chores for the user.

#### `tool_remove_personal_chore`
Archives a personal chore.
```python
RemovePersonalChore(
    chore_title_fuzzy="gym"
)
```

### Scheduler Jobs

#### `send_personal_chore_reminders`
Runs daily at 8:00 AM:
- Sends DM reminders for personal chores due today
- Only active chores are included
- Reminders sent only to chore owner

#### `auto_verify_personal_chores`
Runs every hour:
- Finds logs with status "PENDING" older than 48 hours
- Automatically approves them
- Sends notification to owner about auto-verification

## Privacy Design

Personal chores are isolated at every level:

### Database Layer
- All queries filter by `owner_phone`
- No cross-user data leakage possible
- Accountability partners can only see specific logs they're assigned to verify

### Service Layer
- Ownership validation before any operation
- Partner relationship validated before verification
- Stats only accessible to owner (no admin override)

### Agent Layer
- Tools enforce ownership checks
- Partner must be active household member
- Auto-converts to self-verified if partner becomes inactive

### Notification Layer
- Personal chore notifications always sent via DM
- Never appear in group chat
- No visibility to other household members

## User Experience Flows

### Example 1: Self-Verified Personal Chore
```
User: /personal add meditate every morning
Bot: ✅ Created personal chore "Meditate" (every morning). Self-verified.

[Next morning - DM only]
Bot: 🧘 Personal Chore Reminder: Meditate

User: done meditate
Bot: ✅ Logged "Meditate". Nice work! Keep the streak going.

User: /personal stats
Bot: 📊 Your Personal Stats (Last 30 Days)
     Active Chores: 1
     Completions: 5 (71% on-time)
     Pending Verifications: 0
```

### Example 2: Accountability Partner Workflow
```
User A: /personal add gym every 2 days accountability:@Bob
Bot: ✅ Created personal chore "Gym" (every 2 days). Bob will verify your completions.

[2 days later]
User A: done gym
Bot → User A (DM): ✅ Logged "Gym". Awaiting verification from Bob.
Bot → Bob (DM): 💪 Alice claims she completed "Gym". Please verify.
                Use: /personal verify [log_id] approve/reject

Bob: /personal verify pcl_xyz approve Great job!
Bot → Alice: ✅ Bob verified your "Gym" completion: Great job!
Bot → Bob: ✅ Verified Alice's "Gym". Keep it up!
```

### Example 3: Name Collision Handling
```
Admin: /define gym every 3 days  # Household chore
User: /personal add gym every 2 days  # Personal chore

User: done gym
Bot: I found both a household chore "Gym" and your personal chore "Gym".
     Which one did you complete? Reply 'household' or 'personal'.

User: personal
Bot: ✅ Logged "Gym" (personal). Nice work!
```

### Example 4: Partner Leaving Household
```
[Bob's status changed to BANNED or LEFT]

Bot → Alice (DM): Bob is no longer in the household. Your personal chore "Gym"
                  has been converted to self-verified.

User A: done gym
Bot: ✅ Logged "Gym". Nice work!  # Auto-verified, no partner notification
```

## Edge Cases Handled

### 1. Invalid Accountability Partner
**Scenario**: User specifies non-existent or non-active user
**Handling**: Bot validates and responds with error message listing valid household members

### 2. Partner Becomes Inactive
**Scenario**: Accountability partner leaves household or is banned
**Handling**: Auto-converts chore to self-verified, notifies owner

### 3. Auto-Verification Timeout
**Scenario**: Partner doesn't verify within 48 hours
**Handling**: Scheduler automatically approves log, notifies owner

### 4. Fuzzy Matching Ambiguity
**Scenario**: Multiple personal chores match the fuzzy query
**Handling**: Bot lists matches and asks user to clarify

### 5. Privacy in Group Chat
**Scenario**: User says "done gym" in group chat (personal chore exists)
**Handling**: Bot sends DM confirmation, doesn't respond in group

## Testing

### Unit Tests
- `tests/unit/test_personal_chore_service.py`: Service layer CRUD operations (98% coverage)
- `tests/unit/test_personal_verification_service.py`: Verification flow and stats (84% coverage)

### Integration Tests
- `tests/integration/test_personal_chore_workflows.py`: End-to-end workflows
  - Self-verified workflow
  - Accountability partner workflow (approve/reject)
  - Auto-verification after 48 hours
  - Privacy isolation
  - Partner leaving household
  - Fuzzy matching
  - Wrong partner verification prevention
  - Delete chore

### Coverage Summary
- **personal_chore_service.py**: 98% (47 statements, 1 miss)
- **personal_verification_service.py**: 84% (101 statements, 16 misses)
- **319 tests passed** (28 integration tests skipped without PocketBase)

## Performance Considerations

### Database Queries
- Indexed on `owner_phone` for fast filtering
- Indexed on `personal_chore_id` for log lookups
- Indexed on `verification_status` for pending verifications

### Caching
- No caching implemented (privacy > performance)
- Personal data intentionally not cached to avoid leaks

### Scheduler Performance
- Auto-verification: O(n) where n = pending logs
- Reminders: O(m) where m = active chores for all users
- Both run efficiently with proper indexing

## Security & Privacy

### Ownership Enforcement
Every operation validates:
1. User owns the chore
2. User is the accountability partner (for verifications)
3. User is active household member

### Data Access Control
- No admin override for personal chores
- No cross-user queries possible
- Accountability partners can only see assigned logs

### Audit Trail
- All operations logged via Logfire
- No PII exposed in logs
- Operation metadata includes user context

## Future Enhancements

### Potential v2 Features
- **Habit Streaks**: Visual streak tracking (🔥 7 day streak!)
- **Personal Goals**: Monthly targets (e.g., "Gym 20 times this month")
- **Categories**: Tag personal chores (fitness, work, hobbies)
- **Export**: Download history as CSV
- **Multiple Partners**: Assign multiple accountability partners per chore
- **Calendar Integration**: Sync with Google Calendar / iCal

### Out of Scope
- Public sharing of personal achievements (privacy-first design)
- Personal leaderboards (creates comparison pressure)
- Integration with household point system (keeps systems separate)

## Troubleshooting

### "Chore not found" errors
- Check spelling (fuzzy matching is case-insensitive)
- Ensure chore exists: `/personal list`
- Verify chore wasn't archived

### Partner verification not working
- Confirm partner is active household member
- Check partner phone number is correct
- Verify 48-hour timeout hasn't passed (auto-verified)

### Reminders not sent
- Check scheduler is running: `scheduler.get_jobs()`
- Verify chore has recurrence pattern
- Confirm chore status is "ACTIVE"

## Related Documentation

- [Architecture Decisions](../adrs/) - System design philosophy
- [Agent Tools](../AGENTS.md) - Tool development guide
- [Database Schema](../src/core/schema.py) - Collection definitions
- [Scheduler Jobs](../src/core/scheduler.py) - Job scheduling

## Support

For questions or issues:
1. Check this documentation
2. Review test files for examples
3. Contact the development team
