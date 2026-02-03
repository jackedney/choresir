# ADR 004: Deterministic Conflict Resolution

**Status:** Accepted  
**Date:** 2026-01-14

## Context

Disputes will occur (User A says "Done", User B says "Not Clean"). The system needs a rule to resolve this without a human administrator, as there is no "Manager" in a household context.

## Decision

We will implement a **Math-Based Jury System**.

1. **Odd Population:** Trigger a majority vote among remaining members.
2. **Even Population:** Trigger a "Deadlock" state.
   - **Resolution:** The chore remains stuck in `CONFLICT` until a user manually overrides it (or the users resolve it verbally and re-attempt the log). There is no algorithmic tie-breaker.

**Voting Rules:**

- **Anonymity:** Votes are anonymous. The system will announce the result ("3 votes to Reject"), not the voters.
- **Anti-Griefing:** None. We rely on social trust. If a user trolls the system by rejecting everything, the household must solve that socially.

**Alternatives Rejected:**

- "Random Coin Toss" - feels unfair
- "Assignee Wins" - defeats the purpose of verification

## Consequences

### Positive

- Removes the bot from being the "Bad Guy"; outsources judgment to the group.
- Forces democratic participation.

### Negative

- In a 2-person household, the "Deadlock" feature effectively freezes the app until they talk.

### Acceptance

This is a feature, not a bug. The app forces verbal resolution rather than arbitrary algorithmic decisions.

## Related ADRs

- [ADR 003: Verification Protocol](003-verification.md) - Establishes verification requirement
- [ADR 008: Gamification](008-gamification.md) - Leaderboards affected by conflict resolution
