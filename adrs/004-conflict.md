# ADR 004: Deterministic Conflict Resolution

## Status
Accepted

## Date
2026-01-14

## Context
Disputes will occur (User A says "Done", User B says "Not Clean"). The system needs a rule to resolve this without a human administrator, as there is no "Manager" in a household context.

## Decision
We will implement a **Math-Based Jury System**.

1.  **Odd Population**: Trigger a majority vote among remaining members.
2.  **Even Population**: Trigger a "Deadlock" state that blocks the chore until a manual override occurs.

We rejected "Random Coin Toss" as it feels unfair.
We rejected "Assignee Wins" as it defeats the purpose of verification.

## Consequences

### Positive
*   Removes the bot from being the "Bad Guy"; outsources judgment to the group.
*   Forces democratic participation.

### Negative
*   In a 2-person household, the "Deadlock" feature effectively freezes the app until they talk.

### Acceptance
This is a feature, not a bug. The app forces verbal resolution rather than arbitrary algorithmic decisions.