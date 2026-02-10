"""Task tools for choresir agent.

Merges chore management, verification, and analytics tools into a single module.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

import src
from src.agents.base import Deps
from src.core.fuzzy_match import fuzzy_match, fuzzy_match_all
from src.core.recurrence_parser import cron_to_human
from src.domain.task import TaskState
from src.models.service_models import (
    CompletionRate,
    LeaderboardEntry,
    OverdueChore,
    UserStatistics,
)
from src.modules.tasks import deletion, service, verification


logger = logging.getLogger(__name__)

# Title threshold constants for user stats
TITLE_THRESHOLD_MACHINE = 10
TITLE_THRESHOLD_CONTRIBUTOR = 5
TITLE_THRESHOLD_STARTER = 1

# Period constants for analytics
PERIOD_WEEKLY_DAYS = 7
PERIOD_MONTHLY_DAYS = 30


class DefineChore(BaseModel):
    """Parameters for defining a new chore."""

    title: str = Field(description="Chore title (e.g., 'Take out trash')")
    recurrence: str = Field(description="Recurrence string (e.g., 'every 3 days' or CRON format)")
    assignee_phone: str | None = Field(
        default=None,
        description="Phone number of user to assign chore to (None for unassigned)",
    )
    description: str = Field(default="", description="Optional detailed description")


class LogChore(BaseModel):
    """Parameters for logging a chore completion."""

    chore_title_fuzzy: str = Field(description="Chore title or partial match (fuzzy search)")
    notes: str | None = Field(default=None, description="Optional notes about completion")
    is_swap: bool = Field(
        default=False,
        description="True if this is a Robin Hood swap (one user doing another's chore)",
    )


class RequestChoreDeletion(BaseModel):
    """Parameters for requesting chore deletion."""

    chore_title_fuzzy: str = Field(description="Chore title or partial match (fuzzy search)")
    reason: str = Field(default="", description="Optional reason for requesting deletion")


class RespondToDeletion(BaseModel):
    """Parameters for responding to a deletion request."""

    workflow_id: str | None = Field(
        default=None,
        description="Workflow ID (optional, for direct reference)",
    )
    chore_title_fuzzy: str | None = Field(
        default=None,
        description="Chore title or partial match (fuzzy search, used if workflow_id not provided)",
    )
    decision: str = Field(description="Decision: 'approve' or 'reject'")
    reason: str = Field(default="", description="Optional reason for decision")


class BatchRespondToWorkflows(BaseModel):
    """Parameters for batch responding to multiple workflows."""

    workflow_ids: list[str] | None = Field(
        default=None,
        description="List of workflow IDs to action (optional, for direct reference)",
    )
    indices: list[int] | None = Field(
        default=None,
        description="List of 1-based indices from 'REQUESTS YOU CAN ACTION' section (optional)",
    )
    decision: str = Field(description="Decision: 'approve' or 'reject'")
    reason: str = Field(default="", description="Optional reason for decision")


class VerifyChore(BaseModel):
    """Parameters for verifying a chore completion."""

    workflow_id: str | None = Field(
        default=None,
        description="Workflow ID (optional, for direct reference)",
    )
    chore_title_fuzzy: str | None = Field(
        default=None,
        description="Chore title or partial match (fuzzy search, used if workflow_id not provided)",
    )
    decision: Literal["APPROVE", "REJECT"] = Field(description="Verification decision")
    reason: str | None = Field(default=None, description="Optional reason for decision")


class ListMyChores(BaseModel):
    """Parameters for listing household chores assigned to a user."""

    target_user_phone: str | None = Field(
        default=None,
        description="Phone number of user to list chores for (None for requesting user)",
    )
    time_range: int = Field(
        default=7,
        description="Number of days to look back (default: 7)",
    )


class GetAnalytics(BaseModel):
    """Parameters for getting analytics."""

    metric: Literal["leaderboard", "completion_rate", "overdue"] = Field(
        description="Type of analytics metric to retrieve"
    )
    period_days: int = Field(default=30, description="Number of days to look back (default: 30)")


class GetStats(BaseModel):
    """Parameters for getting user statistics."""

    period_days: int = Field(
        default=7,
        description="Number of days to look back for statistics (default: 7 for weekly)",
    )


def _format_chore_list(chores: list[dict], user_name: str) -> str:
    """
    Format chore list for WhatsApp display.

    Args:
        chores: List of chore records
        user_name: Name of user

    Returns:
        Formatted chore list
    """
    if not chores:
        return f"{user_name} has no household chores assigned."

    now = datetime.now().astimezone()
    lines = [f"{user_name}'s Household Chores:"]

    # Group by state (compare as strings for robustness)
    todo_chores = [c for c in chores if c.get("current_state") == "TODO"]
    pending_chores = [c for c in chores if c.get("current_state") == "PENDING_VERIFICATION"]

    # Show TODO chores with deadlines
    for chore in sorted(todo_chores, key=lambda c: c.get("deadline", "")):
        deadline_str = chore.get("deadline", "")
        if deadline_str:
            deadline = datetime.fromisoformat(deadline_str)
            # Make naive datetimes timezone-aware for comparison
            if deadline.tzinfo is None:
                deadline = deadline.astimezone()
            status = "OVERDUE" if deadline < now else deadline.strftime("%b %d")
        else:
            status = "no deadline"
        lines.append(f"• {chore['title']} (due {status})")

    # Show pending verification
    for chore in pending_chores:
        lines.append(f"• {chore['title']} (pending verification)")

    return "\n".join(lines)


async def _get_workflow_by_id(workflow_id: str) -> dict | str:
    """Get and validate a deletion workflow by ID.

    Args:
        workflow_id: The workflow ID to look up

    Returns:
        The workflow dict if valid, or an error message string
    """
    import src.services.workflow_service

    workflow = await src.services.workflow_service.get_workflow(workflow_id=workflow_id)
    if not workflow:
        return f"Error: Workflow '{workflow_id}' not found."

    if workflow["type"] != src.services.workflow_service.WorkflowType.DELETION_APPROVAL.value:
        return f"Error: Workflow '{workflow_id}' is not a deletion approval workflow."

    if workflow["status"] != src.services.workflow_service.WorkflowStatus.PENDING.value:
        return f"Error: Workflow '{workflow_id}' is not pending (status: {workflow['status']})."

    return workflow


async def _get_workflow_by_chore_title(chore_title_fuzzy: str) -> dict | str:
    """Find a deletion workflow by chore title matching.

    Args:
        chore_title_fuzzy: The chore title to fuzzy match

    Returns:
        The workflow dict if found, or an error message string
    """
    # Get all chores to fuzzy match
    all_chores = await service.get_chores()

    matched_chores = fuzzy_match_all(all_chores, chore_title_fuzzy)

    if not matched_chores:
        return (
            f'No chore found matching "{chore_title_fuzzy}". '
            'To delete a chore, first request deletion with "Request deletion [chore title]".'
        )

    # Find which matched chores have pending deletion requests
    chores_with_pending_deletion = []
    for chore in matched_chores:
        pending_workflow = await deletion.get_pending_deletion_workflow(chore_id=chore["id"])
        if pending_workflow:
            chores_with_pending_deletion.append((chore, pending_workflow))

    if not chores_with_pending_deletion:
        return (
            f'No pending deletion request found for "{chore_title_fuzzy}". '
            'To delete a chore, first request deletion with "Request deletion [chore title]".'
        )

    if len(chores_with_pending_deletion) > 1:
        chore_list = ", ".join(f"'{c['title']}'" for c, _ in chores_with_pending_deletion)
        return f"Multiple chores with pending deletion found: {chore_list}. Please specify which one."

    # Exactly one chore with pending deletion - use it
    _matched_chore, pending_workflow = chores_with_pending_deletion[0]
    return pending_workflow


async def _resolve_deletion_workflow(
    workflow: dict,
    user_id: str,
    decision_lower: str,
    reason: str,
) -> str:
    """Resolve a deletion workflow with given decision.

    Args:
        workflow: The workflow to resolve
        user_id: The resolving user's ID
        decision_lower: The normalized decision ('approve' or 'reject')
        reason: Reason for decision

    Returns:
        Success message
    """
    import src.services.user_service
    import src.services.workflow_service

    resolver = await src.services.user_service.get_user_by_id(user_id=user_id)
    resolver_name = resolver.get("name", "Unknown")

    if decision_lower == "approve":
        await src.services.workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=user_id,
            resolver_name=resolver_name,
            decision=src.services.workflow_service.WorkflowStatus.APPROVED,
            reason=reason,
        )
        return f"Approved deletion of '{workflow['target_title']}'. The chore has been archived."

    await src.services.workflow_service.resolve_workflow(
        workflow_id=workflow["id"],
        resolver_user_id=user_id,
        resolver_name=resolver_name,
        decision=src.services.workflow_service.WorkflowStatus.REJECTED,
        reason=reason,
    )
    return f"Rejected deletion request for '{workflow['target_title']}'. The chore will remain active."


def _resolve_workflow_ids_from_indices(
    indices: list[int],
    actionable_workflows: list[dict],
) -> list[str] | str:
    """Resolve workflow IDs from 1-based indices.

    Args:
        indices: List of 1-based indices
        actionable_workflows: List of actionable workflow dicts

    Returns:
        List of workflow IDs, or an error message string
    """
    if not actionable_workflows:
        return "No actionable workflows found. You have no pending requests from others to approve or reject."

    # Check for 'all' keyword (indices = [0] or user said 'all')
    if len(indices) == 1 and indices[0] == 0:
        return [wf["id"] for wf in actionable_workflows]

    # Convert 1-based indices to workflow IDs
    workflow_ids: list[str] = []
    for idx in indices:
        if 1 <= idx <= len(actionable_workflows):
            workflow_ids.append(actionable_workflows[idx - 1]["id"])
        else:
            logger.warning(
                "Index out of range",
                extra={
                    "index": idx,
                    "total_workflows": len(actionable_workflows),
                },
            )

    return workflow_ids


async def _get_batch_workflow_ids(
    params: BatchRespondToWorkflows,
    user_id: str,
) -> list[str] | str:
    """Determine which workflow IDs to resolve based on params.

    Args:
        params: Batch workflow response parameters
        user_id: The user ID for looking up actionable workflows

    Returns:
        List of workflow IDs, or an error message string
    """
    import src.services.workflow_service

    if params.workflow_ids:
        return params.workflow_ids

    if params.indices:
        actionable_workflows = await src.services.workflow_service.get_actionable_workflows(user_id=user_id)
        result = _resolve_workflow_ids_from_indices(params.indices, actionable_workflows)
        if isinstance(result, str):
            return result
        if not result:
            return "No valid workflows to action. Check the indices or workflow IDs provided."

    return "Error: Either workflow_ids or indices must be provided."


async def _batch_resolve_and_format(
    workflow_ids: list[str],
    user_id: str,
    decision_lower: str,
    reason: str,
) -> str:
    """Batch resolve workflows and format response message.

    Args:
        workflow_ids: List of workflow IDs to resolve
        user_id: The resolving user's ID
        decision_lower: The normalized decision ('approve' or 'reject')
        reason: Optional reason for decision

    Returns:
        Summary message of resolved workflows
    """
    import src.services.user_service
    import src.services.workflow_service

    resolver = await src.services.user_service.get_user_by_id(user_id=user_id)
    resolver_name = resolver.get("name", "Unknown")

    decision_status = (
        src.services.workflow_service.WorkflowStatus.APPROVED
        if decision_lower == "approve"
        else src.services.workflow_service.WorkflowStatus.REJECTED
    )

    resolved_workflows = await src.services.workflow_service.batch_resolve_workflows(
        workflow_ids=workflow_ids,
        resolver_user_id=user_id,
        resolver_name=resolver_name,
        decision=decision_status,
        reason=reason,
    )

    if not resolved_workflows:
        return (
            "No workflows were resolved. You may have tried to approve your own requests or already-resolved workflows."
        )

    # Build summary message
    action_verb = "Approved" if decision_lower == "approve" else "Rejected"
    workflow_titles = [wf["target_title"] for wf in resolved_workflows]
    titles_quoted = '", "'.join(workflow_titles)

    if len(resolved_workflows) == 1:
        return f'{action_verb} 1 workflow: "{titles_quoted}"'
    return f'{action_verb} {len(resolved_workflows)} workflows: "{titles_quoted}"'


async def _get_verification_workflow_by_id(workflow_id: str) -> dict | str:
    """Get and validate a verification workflow by ID.

    Args:
        workflow_id: The workflow ID to look up

    Returns:
        The workflow dict if valid, or an error message string
    """
    import src.services.workflow_service

    workflow = await src.services.workflow_service.get_workflow(workflow_id=workflow_id)
    if not workflow:
        return f"Error: Workflow '{workflow_id}' not found."

    if workflow["type"] != src.services.workflow_service.WorkflowType.TASK_VERIFICATION.value:
        return f"Error: Workflow '{workflow_id}' is not a task verification workflow."

    if workflow["status"] != src.services.workflow_service.WorkflowStatus.PENDING.value:
        return f"Error: Workflow '{workflow_id}' is not pending (status: {workflow['status']})."

    return workflow


async def _get_verification_workflow_by_chore_title(chore_title_fuzzy: str) -> dict | str:
    """Find a verification workflow by chore title matching.

    Args:
        chore_title_fuzzy: The chore title to fuzzy match

    Returns:
        The workflow dict if found, or an error message string
    """
    # Get all chores to fuzzy match
    all_chores = await service.get_chores()

    matched_chores = fuzzy_match_all(all_chores, chore_title_fuzzy)

    if not matched_chores:
        return f'No chore found matching "{chore_title_fuzzy}".'

    # Find which matched chores have pending verification requests
    chores_with_pending_verification = []
    for chore in matched_chores:
        pending_workflow = await verification.get_pending_verification_workflow(chore_id=chore["id"])
        if pending_workflow:
            chores_with_pending_verification.append((chore, pending_workflow))

    if not chores_with_pending_verification:
        return f'No pending verification found for "{chore_title_fuzzy}".'

    if len(chores_with_pending_verification) > 1:
        chore_list = ", ".join(f"'{c['title']}'" for c, _ in chores_with_pending_verification)
        return f"Multiple chores with pending verification found: {chore_list}. Please specify which one."

    # Exactly one chore with pending verification - use it
    matched_chore, pending_workflow = chores_with_pending_verification[0]
    return pending_workflow


async def _resolve_verification_workflow(
    workflow: dict,
    user_id: str,
    decision_lower: str,
    reason: str,
) -> str:
    """Resolve a verification workflow with given decision.

    Args:
        workflow: The workflow to resolve
        user_id: The resolving user's ID
        decision_lower: The normalized decision ('approve' or 'reject')
        reason: Optional reason for decision

    Returns:
        Success message
    """
    import src.services.user_service
    import src.services.workflow_service

    resolver = await src.services.user_service.get_user_by_id(user_id=user_id)
    resolver_name = resolver.get("name", "Unknown")

    workflow_decision = (
        src.services.workflow_service.WorkflowStatus.APPROVED
        if decision_lower == "approve"
        else src.services.workflow_service.WorkflowStatus.REJECTED
    )

    await src.services.workflow_service.resolve_workflow(
        workflow_id=workflow["id"],
        resolver_user_id=user_id,
        resolver_name=resolver_name,
        decision=workflow_decision,
        reason=reason,
    )

    if decision_lower == "approve":
        return f"Approved verification of '{workflow['target_title']}'."
    return f"Rejected verification of '{workflow['target_title']}'. Chore has been returned to TODO."


def _format_leaderboard(leaderboard: list[LeaderboardEntry], period_days: int) -> str:
    """
    Format leaderboard for WhatsApp display.

    Args:
        leaderboard: List of leaderboard entries
        period_days: Period in days

    Returns:
        Formatted leaderboard message
    """
    if not leaderboard:
        return f"No completions in last {period_days} days."

    # Show top 3 (or fewer if less than 3 users)
    top_n = min(3, len(leaderboard))
    lines = [f"🏆 Top {top_n} ({period_days} days):"]

    for i, entry in enumerate(leaderboard[:top_n], start=1):
        name = entry.user_name
        count = entry.completion_count
        lines.append(f"{i}. {name} ({count})")

    return "\n".join(lines)


def _format_completion_rate(stats: CompletionRate) -> str:
    """
    Format completion rate for WhatsApp display.

    Args:
        stats: Completion rate statistics

    Returns:
        Formatted completion rate message
    """
    total = stats.total_completions
    period = stats.period_days

    if total == 0:
        return f"No completions in last {period} days."

    on_time_pct = stats.on_time_percentage
    overdue_pct = stats.overdue_percentage

    return (
        f"📊 Completion Rate ({period} days):\nTotal: {total} chores\nOn-time: {on_time_pct}%\nOverdue: {overdue_pct}%"
    )


def _format_overdue_chores(chores: list[OverdueChore]) -> str:
    """
    Format overdue chores for WhatsApp display.

    Args:
        chores: List of overdue chore records

    Returns:
        Formatted overdue chores message
    """
    if not chores:
        return "✅ No overdue chores!"

    now = datetime.now(UTC)
    lines = [f"⚠️ {len(chores)} overdue chore(s):"]

    for chore in chores[:5]:
        title = chore.title
        deadline = datetime.fromisoformat(chore.deadline)
        # If deadline is naive (no timezone), assume UTC
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        days_overdue = (now - deadline).days

        if days_overdue == 0:
            time_str = "today"
        elif days_overdue == 1:
            time_str = "1 day"
        else:
            time_str = f"{days_overdue} days"

        lines.append(f"• '{title}' ({time_str})")

    max_display = 5
    if len(chores) > max_display:
        lines.append(f"... and {len(chores) - max_display} more")

    return "\n".join(lines)


def _format_user_stats(stats: UserStatistics, period_days: int) -> str:
    """Format user statistics for WhatsApp display.

    Args:
        stats: User statistics dictionary
        period_days: Period in days for context

    Returns:
        Formatted stats message
    """
    rank_str = f"#{stats.rank}" if stats.rank is not None else "Not ranked yet"
    completions = stats.completions
    pending = stats.claims_pending
    overdue = stats.overdue_chores

    # Build dynamic title based on performance
    if completions >= TITLE_THRESHOLD_MACHINE:
        title = "🏆 The Machine"
    elif completions >= TITLE_THRESHOLD_CONTRIBUTOR:
        title = "💪 Solid Contributor"
    elif completions >= TITLE_THRESHOLD_STARTER:
        title = "👍 Getting Started"
    else:
        title = "😴 The Observer"

    # Build period label
    if period_days == PERIOD_WEEKLY_DAYS:
        period_label = "This Week"
    elif period_days == PERIOD_MONTHLY_DAYS:
        period_label = "This Month"
    else:
        period_label = f"Last {period_days} Days"

    lines = [
        f"📊 *Your Stats ({period_label})*",
        "",
        f"*{title}*",
        "",
        f"Rank: {rank_str}",
        f"Chores Completed: {completions}",
        f"Pending Verification: {pending}",
        f"Overdue: {overdue}",
    ]

    # Add encouragement/warning based on status
    if overdue and overdue > 0:
        lines.append("")
        lines.append(f"⚠️ You have {overdue} overdue chore(s)!")
    elif completions == 0:
        lines.append("")
        lines.append("💡 Complete a chore to get on the board!")

    return "\n".join(lines)


async def tool_define_chore(ctx: RunContext[Deps], params: DefineChore) -> str:
    """
    Define a new chore with recurrence schedule.

    Args:
        ctx: Agent runtime context with dependencies
        params: Chore definition parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_define_chore", title=params.title):
            # If assignee phone is provided, look up user ID
            assignee_id = None
            if params.assignee_phone:
                user = await src.services.user_service.get_user_by_phone(phone=params.assignee_phone)
                if not user:
                    return f"Error: User with phone {params.assignee_phone} not found."
                assignee_id = user["id"]

            # Create chore
            chore = await service.create_chore(
                title=params.title,
                description=params.description,
                recurrence=params.recurrence,
                assigned_to=assignee_id,
            )

            # Convert schedule to human-readable format
            schedule_human = cron_to_human(chore.get("schedule_cron", params.recurrence))
            assignee_msg = f"assigned to {params.assignee_phone}" if assignee_id else "unassigned"
            return f"Created chore '{params.title}' - {schedule_human}, {assignee_msg}."

    except ValueError as e:
        logger.warning("Chore creation failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_define_chore", extra={"error": str(e), "type": type(e).__name__})
        return f"Error: Unable to create chore - {e!s}"


async def tool_log_chore(ctx: RunContext[Deps], params: LogChore) -> str:
    """
    Log a chore completion and request verification.

    Supports fuzzy matching for chore titles and Robin Hood swaps.
    Checks for name collisions with personal chores.
    Enforces weekly takeover limits for Robin Hood swaps.

    Args:
        ctx: Agent runtime context with dependencies
        params: Chore logging parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_log_chore", title=params.chore_title_fuzzy, is_swap=params.is_swap):
            # Get all household chores to fuzzy match
            all_chores = await service.get_chores()

            # Fuzzy match household chore
            household_match = fuzzy_match(all_chores, params.chore_title_fuzzy)

            # Get user's personal chores to check for collision
            user = await src.services.user_service.get_user_by_phone(phone=ctx.deps.user_phone)
            if user:
                personal_chores = await service.get_personal_chores(
                    owner_id=user["id"],
                    include_archived=False,
                )
                personal_match = service.fuzzy_match_task(personal_chores, params.chore_title_fuzzy)
            else:
                personal_chores = []
                personal_match = None

            # Check for collision
            if household_match and personal_match:
                return (
                    f"I found both a household chore '{household_match['title']}' and "
                    f"your personal chore '{personal_match['title']}'. "
                    f"Please be more specific: use '/personal done {params.chore_title_fuzzy}' "
                    f"for personal chores or provide full household chore name."
                )

            # No collision - proceed with household chore logging
            if not household_match:
                return f"Error: No household chore found matching '{params.chore_title_fuzzy}'."

            # Check if chore is in TODO state
            if household_match["current_state"] != TaskState.TODO:
                return (
                    f"Error: Chore '{household_match['title']}' is in state '{household_match['current_state']}' "
                    "and cannot be logged right now."
                )

            # Robin Hood Protocol: Check if this is a swap and enforce weekly limits
            if params.is_swap:
                # Verify that claimer is not original assignee
                if household_match["assigned_to"] == ctx.deps.user_id:
                    return (
                        f"Error: You are already assigned to '{household_match['title']}'. "
                        f"Robin Hood swaps are only for taking over another member's chore."
                    )

                # Check weekly takeover limit
                import src.modules.tasks.robin_hood as robin_hood_service

                can_takeover, error_message = await robin_hood_service.can_perform_takeover(ctx.deps.user_id)
                if not can_takeover:
                    return f"Error: {error_message}"

                # Increment takeover count
                await robin_hood_service.increment_weekly_takeover_count(ctx.deps.user_id)

            # At this point, household_match is guaranteed to be not None
            assert household_match is not None
            chore_id = household_match["id"]
            chore_title = household_match["title"]

            # Log completion
            await verification.request_verification(
                chore_id=chore_id,
                claimer_user_id=ctx.deps.user_id,
                notes=params.notes or "",
                is_swap=params.is_swap,
            )

            swap_msg = " (Robin Hood swap)" if params.is_swap else ""
            return (
                f"Logged completion of '{chore_title}'{swap_msg}. Awaiting verification from another household member."
            )

    except ValueError as e:
        logger.warning("Chore logging failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_log_chore", extra={"error": str(e)})
        return "Error: Unable to log chore. Please try again."


async def tool_request_chore_deletion(ctx: RunContext[Deps], params: RequestChoreDeletion) -> str:
    """
    Request deletion of a household chore (requires another member to approve).

    This initiates a two-step deletion process. Another household member
    must approve deletion within 48 hours for chore to be removed.

    Args:
        ctx: Agent runtime context with dependencies
        params: Deletion request parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_request_chore_deletion", title=params.chore_title_fuzzy):
            # Get all chores to fuzzy match
            all_chores = await service.get_chores()

            # Fuzzy match chore
            matched_chore = service.fuzzy_match_task(all_chores, params.chore_title_fuzzy)

            if not matched_chore:
                return f"Error: No chore found matching '{params.chore_title_fuzzy}'."

            chore_id = matched_chore["id"]
            chore_title = matched_chore["title"]

            # Check if chore is already archived
            if matched_chore["current_state"] == TaskState.ARCHIVED:
                return f"Error: Chore '{chore_title}' is already archived."

            # Request deletion
            log_record = await deletion.request_chore_deletion(
                chore_id=chore_id,
                requester_user_id=ctx.deps.user_id,
                reason=params.reason,
            )

            # Send notifications to other household members
            try:
                import src.services.notification_service

                await src.services.notification_service.send_deletion_request_notification(
                    log_id=log_record["id"],
                    task_id=chore_id,
                    task_title=chore_title,
                    requester_user_id=ctx.deps.user_id,
                )
            except Exception:
                logger.exception(
                    "Failed to send deletion request notifications for chore %s",
                    chore_id,
                )

            return f"Requested deletion of '{chore_title}'. Another household member must approve this within 48 hours."

    except ValueError as e:
        logger.warning("Chore deletion request failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_request_chore_deletion", extra={"error": str(e)})
        return "Error: Unable to request chore deletion. Please try again."


async def tool_respond_to_deletion(ctx: RunContext[Deps], params: RespondToDeletion) -> str:
    """Respond to a pending chore deletion request (approve or reject).

    Supports referencing by workflow_id directly or by chore title matching.

    Args:
        ctx: Agent runtime context with dependencies
        params: Deletion response parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_respond_to_deletion", workflow_id=params.workflow_id, decision=params.decision):
            # Validate input
            if not params.workflow_id and not params.chore_title_fuzzy:
                return "Error: Either workflow_id or chore_title_fuzzy must be provided."

            # Normalize decision
            decision_lower = params.decision.lower().strip()
            if decision_lower not in ("approve", "reject"):
                return f"Error: Invalid decision '{params.decision}'. Must be 'approve' or 'reject'."

            # Determine workflow to resolve
            if params.workflow_id:
                workflow_result = await _get_workflow_by_id(params.workflow_id)
            else:
                assert params.chore_title_fuzzy is not None
                workflow_result = await _get_workflow_by_chore_title(params.chore_title_fuzzy)

            # Check if we got an error message instead of a workflow
            if isinstance(workflow_result, str):
                return workflow_result

            # Resolve workflow
            return await _resolve_deletion_workflow(
                workflow=workflow_result,
                user_id=ctx.deps.user_id,
                decision_lower=decision_lower,
                reason=params.reason or "",
            )

    except ValueError as e:
        logger.warning("Chore deletion response failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_respond_to_deletion", extra={"error": str(e)})
        return "Error: Unable to process deletion response. Please try again."


async def tool_batch_respond_to_workflows(ctx: RunContext[Deps], params: BatchRespondToWorkflows) -> str:
    """Batch approve or reject multiple workflows at once.

    Supports three modes of operation:
    1. Direct workflow IDs: Provide workflow_ids list
    2. Indexed references: Provide indices list (1-based from 'REQUESTS YOU CAN ACTION')
    3. All workflows: Set indices to [0] or 'all' keyword to action all actionable workflows

    Args:
        ctx: Agent runtime context with dependencies
        params: Batch workflow response parameters

    Returns:
        Summary message of resolved workflows or error message
    """
    try:
        with logfire.span("tool_batch_respond_to_workflows", decision=params.decision):
            # Normalize decision
            decision_lower = params.decision.lower().strip()
            if decision_lower not in ("approve", "reject"):
                return f"Error: Invalid decision '{params.decision}'. Must be 'approve' or 'reject'."

            # Determine which workflow IDs to resolve
            workflow_ids_result = await _get_batch_workflow_ids(params, ctx.deps.user_id)
            if isinstance(workflow_ids_result, str):
                return workflow_ids_result

            # Resolve workflows and format response
            return await _batch_resolve_and_format(
                workflow_ids=workflow_ids_result,
                user_id=ctx.deps.user_id,
                decision_lower=decision_lower,
                reason=params.reason or "",
            )

    except ValueError as e:
        logger.warning("Batch workflow response failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_batch_respond_to_workflows", extra={"error": str(e)})
        return "Error: Unable to process batch workflow response. Please try again."


async def tool_verify_chore(ctx: RunContext[Deps], params: VerifyChore) -> str:
    """Verify or reject a chore completion claim.

    Prevents self-verification. Approvals mark chore as completed.
    Rejections return chore to TODO.

    Supports referencing by workflow_id directly or by chore title matching.

    Args:
        ctx: Agent runtime context with dependencies
        params: Verification parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_verify_chore", workflow_id=params.workflow_id, decision=params.decision):
            # Validate input
            if not params.workflow_id and not params.chore_title_fuzzy:
                return "Error: Either workflow_id or chore_title_fuzzy must be provided."

            # Normalize decision
            decision_lower = params.decision.lower().strip()
            if decision_lower not in ("approve", "reject"):
                return f"Error: Invalid decision '{params.decision}'. Must be 'approve' or 'reject'."

            # Determine workflow to resolve
            if params.workflow_id:
                workflow_result = await _get_verification_workflow_by_id(params.workflow_id)
            else:
                assert params.chore_title_fuzzy is not None
                workflow_result = await _get_verification_workflow_by_chore_title(params.chore_title_fuzzy)

            # Check if we got an error message instead of a workflow
            if isinstance(workflow_result, str):
                return workflow_result

            # Resolve workflow
            return await _resolve_verification_workflow(
                workflow=workflow_result,
                user_id=ctx.deps.user_id,
                decision_lower=decision_lower,
                reason=params.reason or "",
            )

    except ValueError as e:
        logger.warning("Verification failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_verify_chore", extra={"error": str(e)})
        return "Error: Unable to verify chore. Please try again."


async def tool_list_my_chores(ctx: RunContext[Deps], params: ListMyChores) -> str:
    """
    List household chores assigned to a user.

    Use this when user asks "what chores do I have?", "my chores", "list chores",
    or wants to see their assigned household tasks. Shows todo, pending, and completed
    chores within time range.

    Args:
        ctx: Agent runtime context with dependencies
        params: Query parameters

    Returns:
        Formatted list of household chores
    """
    try:
        with logfire.span("tool_list_my_chores", target=params.target_user_phone):
            # Determine target user
            if params.target_user_phone:
                target_user = await src.services.user_service.get_user_by_phone(phone=params.target_user_phone)
                if not target_user:
                    return f"Error: User with phone {params.target_user_phone} not found."
                target_user_id = target_user["id"]
                target_user_name = target_user["name"]
            else:
                target_user_id = ctx.deps.user_id
                target_user_name = ctx.deps.user_name

            # Get chores for user in time range
            time_range_start = datetime.now() - timedelta(days=params.time_range)
            chores = await service.get_chores(
                user_id=target_user_id,
                time_range_start=time_range_start,
            )

            return _format_chore_list(chores, target_user_name)

    except Exception:
        logger.exception("Unexpected error in tool_list_my_chores")
        return "Error: Unable to retrieve chores. Please try again."


async def tool_get_analytics(ctx: RunContext[Deps], params: GetAnalytics) -> str:
    """
    Get household analytics and metrics.

    Supports leaderboards, completion rates, and overdue chores.

    Args:
        ctx: Agent runtime context with dependencies
        params: Analytics query parameters

    Returns:
        Formatted analytics message
    """
    try:
        import src.modules.tasks.analytics as analytics_service

        with logfire.span("tool_get_analytics", metric=params.metric, period=params.period_days):
            if params.metric == "leaderboard":
                leaderboard = await analytics_service.get_leaderboard(period_days=params.period_days)
                return _format_leaderboard(leaderboard, params.period_days)

            if params.metric == "completion_rate":
                stats = await analytics_service.get_completion_rate(period_days=params.period_days)
                return _format_completion_rate(stats)

            if params.metric == "overdue":
                chores = await analytics_service.get_overdue_chores()
                return _format_overdue_chores(chores)

            return f"Error: Unknown metric '{params.metric}'."

    except Exception as e:
        logger.error("Unexpected error in tool_get_analytics", extra={"error": str(e)})
        return "Error: Unable to retrieve analytics. Please try again."


async def tool_get_stats(ctx: RunContext[Deps], params: GetStats) -> str:
    """Get your personal chore statistics and leaderboard ranking.

    Use this when user asks for their stats, score, ranking, or standing.
    Common triggers: "stats", "my stats", "score", "how am I doing", "leaderboard".

    Args:
        ctx: Agent runtime context with dependencies
        params: Stats query parameters

    Returns:
        Formatted personal statistics message
    """
    try:
        import src.modules.tasks.analytics as analytics_service

        with logfire.span("tool_get_stats", user_id=ctx.deps.user_id, period=params.period_days):
            # Get user statistics from analytics service
            stats = await analytics_service.get_user_statistics(
                user_id=ctx.deps.user_id,
                period_days=params.period_days,
            )

            return _format_user_stats(stats, params.period_days)

    except Exception as e:
        logger.error("Unexpected error in tool_get_stats", extra={"error": str(e)})
        return "Error: Unable to retrieve your stats. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register task tools with agent."""
    agent.tool(tool_define_chore)
    agent.tool(tool_log_chore)
    agent.tool(tool_request_chore_deletion)
    agent.tool(tool_respond_to_deletion)
    agent.tool(tool_batch_respond_to_workflows)
    agent.tool(tool_verify_chore)
    agent.tool(tool_list_my_chores)
    agent.tool(tool_get_analytics)
    agent.tool(tool_get_stats)
