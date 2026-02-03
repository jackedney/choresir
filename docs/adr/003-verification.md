# ADR 003: Human-in-the-Loop Verification Protocol

**Status:** Accepted  
**Date:** 2026-01-14

## Context

A core problem statement is the lack of accountability in household chores. A system where users simply "self-report" completion is prone to inaccuracy and does not solve the social friction of the problem.

## Decision

We will implement a **Mandatory Verification State Machine**.

- No chore can transition directly from TODO → COMPLETED.
- The transition must be TODO → PENDING_VERIFICATION.
- A different user (The "Verifier") must explicitly approve the transition to COMPLETED.
- If the Verifier rejects, the state moves to CONFLICT.

## Consequences

### Positive

- Enforces social accountability; prevents "gaming" the system.

### Negative

- Increases friction. A user cannot just "check a box"; they must wait for approval.

### Mitigation

- We will allow "Passive Approval" (if no rejection within X hours, auto-approve) in a future iteration if friction becomes too high. For now, strict approval is required.

## Related ADRs

- [ADR 004: Conflict Resolution](004-conflict.md) - Handling disputes when verification fails
- [ADR 009: Interactive Verification](009-interactive-verification.md) - Enhanced verification UX with buttons
