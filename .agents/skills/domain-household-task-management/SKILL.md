---
name: domain-household-task-management
description: Domain knowledge — household task coordination concepts for correct implementation
user-invocable: false
---

# Household Task Management

> Relevance: Choresir's domain logic — tasks, verification, recurrence, takeovers, accountability — must model household dynamics correctly. Getting these wrong produces silent bugs that erode trust.

## Core Concepts

### Task lifecycle

A task moves through states: `PENDING` → `CLAIMED` → `VERIFIED` (or rejected back to `PENDING`).

- **PENDING**: Task exists, no completion claim made.
- **CLAIMED**: A member has asserted they completed it; awaiting verification (if required).
- **VERIFIED**: Completion confirmed. If recurring, resets to PENDING with updated deadline.

Deletion is a separate flow: requires approval from another member before the record is removed.

### Verification modes

Three modes determine who can confirm completion:
- **NONE**: No verification needed — task goes straight to VERIFIED when claimed.
- **PEER**: Any other household member can verify.
- **PARTNER**: Only a specific designated member can verify (e.g., one partner verifies the other's chores).

**Critical invariant**: A member must never verify their own completion claim. This must be enforced at the service layer, not just the UI.

### Visibility

- **Shared tasks**: Visible to all members. Any member can claim, view, or complete them.
- **Personal tasks**: Visible only to the owner. Other members cannot see or interact with them.

### Takeovers

Any member can claim and complete another member's shared task (helpful when someone is busy). This is limited to a configurable maximum per user per week to prevent gaming the leaderboard.

### Recurrence

A recurring task has a schedule (e.g., "every Monday", "daily"). When it is verified complete:
1. Status resets to `PENDING`.
2. The next deadline is calculated from the recurrence schedule, not from the completion time (to prevent drift).

If a recurring task is not completed by its deadline, it becomes overdue — the scheduler sends reminders.

### Completion history

Every completion is recorded: who completed it, who verified it, when, and any feedback from the verifier. This history powers analytics (leaderboards, completion rates) and is immutable once written.

## Mental Models

**Think of tasks like contracts**: A task is an agreement — someone is responsible (`assignee`), and completion must be witnessed (`verifier`). The verification model mirrors real accountability in shared living.

**Think of the job queue like a mailbox**: WAHA delivers a message, you put it in the queue (mailbox) and immediately say "got it". The worker processes it later. The queue survives crashes; the acknowledgment prevents message loss.

**Think of recurrence like a renewal**: When a recurring task is verified, it doesn't "complete and close" — it renews. The next occurrence is scheduled automatically, like a lease renewal.

## Edge Cases & Gotchas

- **Self-verification must be caught at service layer**: The LLM might instruct a tool to verify a task for the same member who claimed it. The service must reject this with `AuthorizationError`, not silently allow it.
- **Rejection returns task to PENDING, not creation**: When a verifier rejects a completion claim, the task status reverts to `PENDING`. The original assignee still owns it and must complete it again.
- **Takeover changes the completer, not the assignee**: If Member B completes Member A's task, the `assignee` remains Member A (who created/was assigned the task), but `CompletionHistory.completed_by` records Member B. Leaderboard logic must use `completed_by`, not `assignee_id`.
- **Recurring task next deadline**: Calculate from the previous scheduled deadline, not from `datetime.now()`. Example: if a weekly task is due Monday and completed Thursday, the next deadline is next Monday — not 7 days from Thursday.
- **Pending member restriction**: Members with `status = "pending"` (not yet onboarded) must not be able to create, complete, or interact with tasks. Check member status in every tool function.
- **Task deletion approval**: A task marked for deletion still exists (and appears in queries) until a second member approves. The task needs a `deletion_requested_by` field and a two-step delete flow.
- **Leaderboard tie-breaking**: When two members have the same completion count, define a consistent tie-breaker (e.g., by `member.id` ascending) so the leaderboard is stable across runs.

## Validation Rules

Invariants that must hold (suitable as property-based test assertions):

1. A member with `status != "active"` never appears as a task completer in a newly created `CompletionHistory`.
2. `CompletionHistory.completed_by_id != CompletionHistory.verified_by_id` always (no self-verification).
3. A task with `verification_mode = NONE` never has `status = CLAIMED` — it skips directly to `VERIFIED`.
4. A recurring task with `status = VERIFIED` always has a `next_deadline` in the future.
5. A member's weekly takeover count never exceeds `settings.max_takeovers_per_week`.
6. A personal task never appears in queries scoped to another member's visible tasks.
