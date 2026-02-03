# ADR 005: Robin Hood Protocol

## Status

Partially Implemented

## Implementation Status

### Currently Implemented
- **Basic swap logging**: The `is_swap` parameter exists in the `LogChore` tool
- **Swap identification**: Code includes "Robin Hood swap" references for tracking takeover operations
- **Weekly limits**: Enforced via `robin_hood_service.py` with 3 takeovers per week limit
- **Point attribution logic**: On-time vs. overdue point distribution implemented in `analytics_service.py`
- **Takeover tracking**: Data model tracks original assignee vs. actual completer

### Not Yet Implemented
- **WhatsApp interface**: No user-facing commands for initiating or managing takeovers
- **Reciprocal exchange**: Optional swap mechanism is not implemented

See completion roadmap in project task tracking for details on remaining implementation items.

## Context

Households often face scheduling conflicts where the person assigned to a chore cannot complete it at the scheduled time. Currently, the system has no mechanism for household members to help each other by taking over chores flexibly. This creates friction and can lead to incomplete chores or manual workarounds outside the system.

We need a way to allow household members to support each other while maintaining accountability and preventing abuse of the system.

## Decision

We will implement the "Robin Hood Protocol" - a chore takeover system that allows any household member to complete another member's assigned chore with the following rules:

### Core Rules

1. **Takeover Availability**: Any household member can take over another member's assigned chore at any time before its deadline expires.

2. **Optional Reciprocal Exchange**: The original assignee MAY optionally take one of the taker's assigned chores in exchange, but this is not required. The takeover is valid whether or not a reciprocal swap occurs.

3. **Point Attribution**:
   - **On-time completion**: Points are awarded to the ORIGINAL assignee (the person who was supposed to do it)
   - **Overdue completion**: Points are awarded to the person who ACTUALLY completed the chore
   - This incentivizes helping teammates while still holding them accountable for overdue tasks

4. **Weekly Limits**: Each household member can participate in a maximum of 3 takeovers per week (either as the taker or the original assignee). This limit resets every Monday at 00:00 in the household's timezone.

### Rationale

- **Flexibility**: Accommodates real-life scheduling conflicts and emergencies
- **Mutual Support**: Encourages household members to help each other
- **Accountability**: Original assignee still gets credit for on-time help, but loses points if they let tasks go overdue
- **Abuse Prevention**: Weekly limits prevent gaming the system or creating dependency patterns
- **Simplicity**: Optional reciprocal exchange keeps the system simple while allowing natural agreements between members

## Consequences

### Positive

- **Increased Flexibility**: Members can manage their own scheduling conflicts more easily
- **Team Collaboration**: Encourages a more cooperative household dynamic
- **Reduced Friction**: Eliminates need for manual reassignments or admin intervention
- **Fair Incentives**: Points system maintains accountability while rewarding helpfulness

### Negative

- **Potential for Gaming**: Members might attempt to game the system, though weekly limits mitigate this
- **Complexity**: Adds additional state tracking (who took over what, reciprocal exchanges, weekly counts)
- **Confusion Risk**: Members might not understand when they get points vs. when the helper gets points
- **Social Dynamics**: Could create social pressure or expectations around helping that some members find uncomfortable

### Technical Implications

1. **Data Model Changes**:
   - Track original assignee vs. actual completer for each chore instance
   - Store takeover count per member per week
   - Record reciprocal exchange relationships (if implemented)

2. **WhatsApp Interface**:
   - New commands for initiating takeover
   - Notifications to both parties when takeover occurs
   - Clear messaging about point attribution rules

3. **Point Calculation Logic**:
   - Check if chore was overdue at completion time
   - Award points to original assignee (on-time) or actual completer (overdue)
   - Ensure weekly limits are enforced before allowing takeovers

4. **Reporting & Analytics**:
   - Track takeover patterns to identify if limits need adjustment
   - Show takeover history in member profiles
   - Highlight helpful members vs. members frequently needing help

## Alternatives Considered

### 1. Simple Reassignment
Allow admins to reassign chores manually.
- **Rejected**: Creates admin burden and doesn't encourage peer-to-peer support

### 2. Required Reciprocal Exchange
Require taker to give one of their chores to the original assignee.
- **Rejected**: Too rigid and creates friction for simple acts of help

### 3. Points Always to Actual Completer
Give points to whoever actually did the chore regardless of timing.
- **Rejected**: Removes accountability for original assignee and could enable dependency

### 4. No Weekly Limits
Allow unlimited takeovers.
- **Rejected**: Opens system to potential abuse and gaming

## Implementation Notes

- Weekly limit counter should reset based on household timezone, not UTC
- Overdue determination should be based on the chore's original due date/time
- Consider adding analytics dashboard to monitor takeover patterns after initial rollout
- May need to adjust weekly limit (3) based on real-world usage data

## Related ADRs

- [ADR 001: Technology Stack](001-stack.md) - Defines the primary user interface (Twilio WhatsApp) through which the Robin Hood Protocol is accessed
- [ADR 012: Natural Language Processing Approach](012-nlp-approach.md) - Describes how takeover commands and requests will be interpreted

## References

- PM Decision documented in AUDIT_PM_DECISIONS.md
- Related to household collaboration and flexibility requirements
