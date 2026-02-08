# Comprehensive Context & Workflow Refactor

## Problem Summary

The bot was designed for 1-on-1 conversations but operates in group chats. This causes:
- **Context isolation**: Each user talks to an isolated instance with no shared group memory
- **Broken references**: "both", "1 and 2", "that" fail without shared context
- **Lost workflows**: Multi-step operations (deletion, verification) scattered across logs

## Solution Overview

### 1. Hybrid Conversation Context
- **Group chats**: Shared conversation archive visible to all members
- **DMs**: Per-user context (current behavior, preserved for privacy)

### 2. Unified Workflow State Machine
- Single `workflows` collection tracking all multi-step operations
- Explicit states, participants, and expiry
- Tools reference workflow IDs instead of fuzzy matching

### 3. Refactored Workflows
- Deletion approval
- Chore verification
- Personal chore verification

---

## Phase 1: Group Conversation Context

### New File: `src/services/group_context_service.py`

```python
"""Group conversation context for shared chat history."""

MAX_GROUP_MESSAGES = 20
GROUP_CONTEXT_TTL_MINUTES = 60

async def add_group_message(*, group_id: str, sender_phone: str, sender_name: str, content: str, is_bot: bool = False) -> None:
    """Record a message in group conversation context."""

async def get_group_context(*, group_id: str) -> list[dict]:
    """Get recent group conversation (all participants)."""

def format_group_context_for_prompt(context: list[dict]) -> str:
    """Format group context showing who said what."""
```

### Changes to `src/agents/choresir_agent.py`

Update `run_agent()` to:
1. Accept `group_id: str | None` parameter
2. If group_id provided, fetch group context instead of per-user context
3. Format as "## RECENT GROUP CONVERSATION" with sender names

### Changes to `src/interface/webhook.py`

Update `_handle_text_message()` and `_handle_user_status()` to:
1. Record messages to group context when `message.is_group_message`
2. Pass `group_id` to `run_agent()`
3. Record bot responses to group context

---

## Phase 2: Workflow State Machine

### New File: `src/services/workflow_service.py`

```python
"""Unified workflow state machine for multi-step operations."""

from enum import StrEnum

class WorkflowType(StrEnum):
    DELETION_APPROVAL = "deletion_approval"
    CHORE_VERIFICATION = "chore_verification"
    PERSONAL_VERIFICATION = "personal_verification"

class WorkflowStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

async def create_workflow(
    *,
    workflow_type: WorkflowType,
    requester_user_id: str,
    target_id: str,  # chore_id or personal_chore_id
    target_title: str,
    expires_hours: int = 48,
    metadata: dict | None = None,
) -> dict:
    """Create a new workflow instance."""

async def get_pending_workflows(
    *,
    workflow_type: WorkflowType | None = None,
    can_be_actioned_by: str | None = None,  # user_id who can approve/reject
) -> list[dict]:
    """Get pending workflows, optionally filtered."""

async def get_user_pending_workflows(*, user_id: str) -> list[dict]:
    """Get workflows the user initiated (awaiting others)."""

async def get_actionable_workflows(*, user_id: str) -> list[dict]:
    """Get workflows the user CAN action (initiated by others)."""

async def resolve_workflow(
    *,
    workflow_id: str,
    resolver_user_id: str,
    decision: WorkflowStatus,
    reason: str = "",
) -> dict:
    """Resolve a workflow (approve/reject)."""

async def batch_resolve_workflows(
    *,
    workflow_ids: list[str],
    resolver_user_id: str,
    decision: WorkflowStatus,
    reason: str = "",
) -> list[dict]:
    """Resolve multiple workflows at once."""

async def expire_old_workflows() -> int:
    """Called by scheduler to expire stale workflows."""
```

### New Collection: `workflows`

Schema:
```
{
    id: string,
    type: WorkflowType,
    status: WorkflowStatus,
    requester_user_id: string,
    requester_name: string,
    target_id: string,
    target_title: string,
    created_at: datetime,
    expires_at: datetime,
    resolved_at: datetime | null,
    resolver_user_id: string | null,
    resolver_name: string | null,
    reason: string,
    metadata: json,
}
```

---

## Phase 3: Refactor Deletion Approval

### Changes to `src/services/deletion_service.py`

Replace scattered log-based tracking with workflow service:

```python
async def request_chore_deletion(...) -> dict:
    # Create workflow instead of log entry
    workflow = await workflow_service.create_workflow(
        workflow_type=WorkflowType.DELETION_APPROVAL,
        requester_user_id=requester_user_id,
        target_id=chore_id,
        target_title=chore["title"],
        expires_hours=48,
    )
    return workflow

async def approve_chore_deletion(...) -> dict:
    # Resolve workflow + archive chore
    await workflow_service.resolve_workflow(...)
    # Archive chore
    ...

# Remove: get_pending_deletion_request() - replaced by workflow_service
# Remove: get_user_pending_deletion_requests() - replaced by workflow_service
# Remove: get_all_pending_deletion_requests() - replaced by workflow_service
```

### Changes to `src/agents/tools/chore_tools.py`

Simplify `tool_respond_to_deletion()`:
- Use workflow_service to find pending deletions
- Support workflow_id reference (not just fuzzy title matching)

Add `tool_batch_respond_to_workflows()`:
- Handle "approve both", "approve all", numbered references
- Reference workflows by ID or index from context

---

## Phase 4: Refactor Chore Verification

### Changes to `src/services/verification_service.py`

Replace log-based tracking with workflow service:

```python
async def request_verification(...) -> dict:
    workflow = await workflow_service.create_workflow(
        workflow_type=WorkflowType.CHORE_VERIFICATION,
        requester_user_id=claimer_user_id,
        target_id=chore_id,
        target_title=chore["title"],
        metadata={"notes": notes, "is_swap": is_swap},
    )
    return workflow

async def verify_chore(...) -> dict:
    await workflow_service.resolve_workflow(...)
    # Update chore state
    ...
```

### Changes to `src/agents/tools/verification_tools.py`

Update tools to use workflow service instead of direct log queries.

---

## Phase 5: Refactor Personal Chore Verification

### Changes to `src/services/personal_chore_service.py`

Similar pattern - use workflow service for accountability partner verification.

---

## Phase 6: Update Agent Context Building

### Changes to `src/agents/choresir_agent.py`

Replace `_build_pending_context()` with `_build_workflow_context()`:

```python
async def _build_workflow_context(user_id: str) -> str:
    """Build context showing all relevant workflows."""

    # Workflows I initiated (awaiting others)
    my_workflows = await workflow_service.get_user_pending_workflows(user_id=user_id)

    # Workflows I can action (initiated by others)
    actionable = await workflow_service.get_actionable_workflows(user_id=user_id)

    lines = []

    if my_workflows:
        lines.append("## YOUR PENDING REQUESTS")
        lines.append("Awaiting approval from another household member:")
        for w in my_workflows:
            lines.append(f"- {w['type']}: \"{w['target_title']}\"")

    if actionable:
        lines.append("")
        lines.append("## REQUESTS YOU CAN ACTION")
        lines.append("These were requested by others - you can approve or reject:")
        for i, w in enumerate(actionable, 1):
            lines.append(f"{i}. [{w['type']}] \"{w['target_title']}\" (from {w['requester_name']})")
        lines.append("")
        lines.append("User can say: 'approve 1', 'reject both', 'approve all', etc.")

    return "\n".join(lines)
```

---

## Phase 7: Update System Prompt

Simplify instructions now that context is properly available:

```python
## Multi-Step Workflows

All approval workflows (deletion, verification) are tracked in the REQUESTS YOU CAN ACTION section.
- Use `tool_respond_to_workflow` for single items
- Use `tool_batch_respond_to_workflows` for "approve both", "approve all", numbered references
- Reference by number (1, 2) or by title

When user says "approve", "yes", "reject":
- Check REQUESTS YOU CAN ACTION for pending items
- If only one item, assume they mean that one
- If multiple, ask which one (or process all if they said "all"/"both")
```

---

## Files to Modify

### New Files
- `src/services/group_context_service.py`
- `src/services/workflow_service.py`

### Modified Files
- `src/agents/choresir_agent.py` - Context building, group support
- `src/interface/webhook.py` - Group context recording
- `src/services/deletion_service.py` - Use workflow service
- `src/services/verification_service.py` - Use workflow service
- `src/services/personal_chore_service.py` - Use workflow service
- `src/agents/tools/chore_tools.py` - Workflow-based tools
- `src/agents/tools/verification_tools.py` - Workflow-based tools (if exists)

### Database
- New collection: `workflows`
- Keep existing collections (logs still used for audit trail)

---

## Migration Strategy

1. Add new services alongside existing code
2. Update tools to use new services
3. Keep old log entries for audit (don't migrate)
4. New workflows use new system
5. Remove deprecated functions after testing

---

## Verification Plan

### Manual Testing
1. Jack requests deletion of 2 chores in group
2. Lottie sees "REQUESTS YOU CAN ACTION" with both listed
3. Lottie says "approve both" - both are approved
4. Jack says "approve" to his own request - error (can't self-approve)

### Unit Tests
- `test_workflow_service.py` - CRUD, expiry, permissions
- `test_group_context_service.py` - Storage, retrieval, TTL

### Integration Tests
- Full deletion flow with workflow service
- Full verification flow with workflow service
- Group context visibility across users

---

## Implementation Order

1. **Phase 1**: Group context service (foundation)
2. **Phase 2**: Workflow service (foundation)
3. **Phase 3**: Deletion refactor (most visible issue)
4. **Phase 4**: Verification refactor
5. **Phase 5**: Personal chore refactor
6. **Phase 6**: Agent context building
7. **Phase 7**: System prompt cleanup
