"""Task CRUD tools for the AI agent."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic_ai import RunContext

from choresir.agent.agent import AgentDeps
from choresir.agent.registry import registry
from choresir.errors import AuthorizationError, NotFoundError

_DOMAIN_ERRORS = (NotFoundError, AuthorizationError)


async def _ensure_active_member(ctx: RunContext[AgentDeps], member_id: int) -> None:
    await ctx.deps.member_service.get_active(member_id)


@registry.register
async def create_task(
    ctx: RunContext[AgentDeps],
    title: str,
    assignee_id: int,
    description: str | None = None,
    deadline: str | None = None,
    recurrence: str | None = None,
    verification_mode: str = "none",
    visibility: str = "shared",
    partner_id: int | None = None,
) -> str:
    """Create a new household task."""
    from choresir.enums import TaskVisibility, VerificationMode

    try:
        await _ensure_active_member(ctx, assignee_id)
        if deadline:
            dl = datetime.fromisoformat(deadline)
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=UTC)
        else:
            dl = None
        task = await ctx.deps.task_service.create_task(
            title=title,
            assignee_id=assignee_id,
            description=description,
            deadline=dl,
            recurrence=recurrence,
            verification_mode=VerificationMode(verification_mode),
            visibility=TaskVisibility(visibility),
            partner_id=partner_id,
        )
        return f"Task '{task.title}' (ID {task.id}) created."
    except (*_DOMAIN_ERRORS, ValueError) as e:
        return str(e)


@registry.register
async def reassign_task(
    ctx: RunContext[AgentDeps],
    task_id: int,
    new_assignee_id: int,
) -> str:
    """Reassign a task to a different household member."""
    try:
        await _ensure_active_member(ctx, new_assignee_id)
        task = await ctx.deps.task_service.reassign(task_id, new_assignee_id)
        return f"Task '{task.title}' reassigned to member {new_assignee_id}."
    except _DOMAIN_ERRORS as e:
        return str(e)


@registry.register
async def delete_task(
    ctx: RunContext[AgentDeps],
    task_id: int,
    requester_id: int,
) -> str:
    """Delete a task. Personal tasks are deleted immediately by owner;
    shared tasks need approval."""
    from choresir.enums import TaskVisibility

    try:
        await _ensure_active_member(ctx, requester_id)
        task = await ctx.deps.task_service.request_deletion(task_id, requester_id)
        if (
            task.visibility == TaskVisibility.PERSONAL
            and task.assignee_id == requester_id
        ):
            return f"Task '{task.title}' deleted."
        return (
            f"Deletion requested for '{task.title}'. "
            f"Needs approval from another member."
        )
    except _DOMAIN_ERRORS as e:
        return str(e)


@registry.register
async def approve_deletion(
    ctx: RunContext[AgentDeps],
    task_id: int,
    approver_id: int,
) -> str:
    """Approve a pending task deletion request."""
    try:
        await _ensure_active_member(ctx, approver_id)
        await ctx.deps.task_service.approve_deletion(task_id, approver_id)
        return f"Task {task_id} deleted."
    except _DOMAIN_ERRORS as e:
        return str(e)


@registry.register
async def list_tasks(
    ctx: RunContext[AgentDeps],
    member_id: int | None = None,
) -> str:
    """List tasks visible to a member, or all tasks."""
    tasks = await ctx.deps.task_service.list_tasks(member_id)
    if not tasks:
        return "No tasks found."
    lines = []
    for t in tasks:
        dl = f", due: {t.deadline.isoformat()}" if t.deadline else ""
        lines.append(f"- [{t.status.value}] {t.title} (ID {t.id}{dl})")
    return "\n".join(lines)
