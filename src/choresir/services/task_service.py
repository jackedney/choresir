"""Task lifecycle: creation, completion, verification, recurrence."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from choresir.enums import TaskStatus, TaskVisibility, VerificationMode
from choresir.errors import AuthorizationError, InvalidTransitionError, NotFoundError
from choresir.models.task import CompletionHistory, Task

_VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.CLAIMED}),
    TaskStatus.CLAIMED: frozenset({TaskStatus.PENDING, TaskStatus.VERIFIED}),
}


def transition_task(task: Task, to: TaskStatus) -> None:
    """Validate and apply a state transition on a task."""
    if to not in _VALID_TRANSITIONS.get(task.status, frozenset()):
        raise InvalidTransitionError(task.status, to)
    task.status = to


def _calculate_next_deadline(current_deadline: datetime, recurrence: str) -> datetime:
    """Advance deadline by the recurrence interval, anchored to the schedule."""
    match recurrence:
        case "daily":
            return current_deadline + timedelta(days=1)
        case "weekly":
            return current_deadline + timedelta(weeks=1)
        case "monthly":
            year = current_deadline.year + (current_deadline.month // 12)
            month = (current_deadline.month % 12) + 1
            max_day = calendar.monthrange(year, month)[1]
            day = min(current_deadline.day, max_day)
            return current_deadline.replace(year=year, month=month, day=day)
        case _:
            msg = f"Unsupported recurrence schedule: {recurrence}"
            raise ValueError(msg)


class TaskService:
    """Task lifecycle: creation, completion, verification."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_task(
        self,
        title: str,
        assignee_id: int,
        description: str | None = None,
        deadline: datetime | None = None,
        recurrence: str | None = None,
        verification_mode: VerificationMode = VerificationMode.NONE,
        visibility: TaskVisibility = TaskVisibility.SHARED,
        partner_id: int | None = None,
    ) -> Task:
        """Create and persist a new task."""
        task = Task(
            title=title,
            assignee_id=assignee_id,
            description=description,
            deadline=deadline,
            next_deadline=deadline,
            recurrence=recurrence,
            verification_mode=verification_mode,
            visibility=visibility,
            partner_id=partner_id,
        )
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def get_task(self, task_id: int) -> Task:
        """Fetch a task by ID, raising NotFoundError if absent."""
        task = await self._session.get(Task, task_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return task

    async def claim_completion(self, task_id: int, member_id: int) -> Task:
        """Claim a task as completed. Skips to VERIFIED when no verification needed."""
        task = await self.get_task(task_id)

        if task.verification_mode == VerificationMode.NONE:
            transition_task(task, TaskStatus.CLAIMED)
            transition_task(task, TaskStatus.VERIFIED)
            history = CompletionHistory(
                task_id=task.id,  # type: ignore[arg-type]
                completed_by_id=member_id,
                completed_at=datetime.now(UTC),
                verified_at=datetime.now(UTC),
            )
            self._session.add(history)
            self._handle_recurrence_reset(task)
        else:
            transition_task(task, TaskStatus.CLAIMED)
            history = CompletionHistory(
                task_id=task.id,  # type: ignore[arg-type]
                completed_by_id=member_id,
                completed_at=datetime.now(UTC),
            )
            self._session.add(history)

        task.updated_at = datetime.now(UTC)
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def verify_completion(
        self,
        task_id: int,
        verifier_id: int,
        feedback: str | None = None,
    ) -> Task:
        """Verify a claimed task, rejecting self-verification."""
        task = await self.get_task(task_id)

        if task.status != TaskStatus.CLAIMED:
            raise InvalidTransitionError(task.status, TaskStatus.VERIFIED)

        # Find who claimed (latest unverified history, or use assignee as fallback)
        result = await self._session.exec(
            select(CompletionHistory)
            .where(
                CompletionHistory.task_id == task_id,
                col(CompletionHistory.verified_at).is_(None),
            )
            .order_by(col(CompletionHistory.completed_at).desc())
        )
        pending_history = result.first()

        # Determine the claimant: from pending history or infer from context
        claimant_id: int | None = (
            pending_history.completed_by_id if pending_history else None
        )

        if verifier_id == claimant_id:
            raise AuthorizationError("Cannot verify your own completion claim")

        if (
            task.verification_mode == VerificationMode.PARTNER
            and verifier_id != task.partner_id
        ):
            raise AuthorizationError("Only the designated partner can verify this task")

        transition_task(task, TaskStatus.VERIFIED)

        now = datetime.now(UTC)
        if pending_history:
            pending_history.verified_by_id = verifier_id
            pending_history.verified_at = now
            pending_history.feedback = feedback
            self._session.add(pending_history)
        else:
            history = CompletionHistory(
                task_id=task.id,  # type: ignore[arg-type]
                completed_by_id=task.assignee_id,
                verified_by_id=verifier_id,
                feedback=feedback,
                completed_at=now,
                verified_at=now,
            )
            self._session.add(history)

        self._handle_recurrence_reset(task)

        task.updated_at = now
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def reject_completion(self, task_id: int, verifier_id: int) -> Task:
        """Reject a completion claim, returning the task to PENDING."""
        task = await self.get_task(task_id)

        if task.status != TaskStatus.CLAIMED:
            raise InvalidTransitionError(task.status, TaskStatus.PENDING)

        # Find the claimant to prevent self-rejection
        result = await self._session.exec(
            select(CompletionHistory)
            .where(
                CompletionHistory.task_id == task_id,
                col(CompletionHistory.verified_at).is_(None),
            )
            .order_by(col(CompletionHistory.completed_at).desc())
        )
        pending_history = result.first()

        claimant_id: int | None = (
            pending_history.completed_by_id if pending_history else None
        )

        if verifier_id == claimant_id:
            raise AuthorizationError("Cannot reject your own completion claim")

        transition_task(task, TaskStatus.PENDING)

        # Remove the unverified history entry
        if pending_history:
            await self._session.delete(pending_history)

        task.updated_at = datetime.now(UTC)
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def reassign(self, task_id: int, new_assignee_id: int) -> Task:
        """Reassign a task to a different member."""
        task = await self.get_task(task_id)
        task.assignee_id = new_assignee_id
        task.updated_at = datetime.now(UTC)
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def request_deletion(self, task_id: int, requester_id: int) -> Task:
        """Mark a task for deletion pending approval."""
        task = await self.get_task(task_id)
        task.deletion_requested_by = requester_id
        task.updated_at = datetime.now(UTC)
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def approve_deletion(self, task_id: int, approver_id: int) -> None:
        """Approve and execute task deletion. Approver must differ from requester."""
        task = await self.get_task(task_id)

        if task.deletion_requested_by is None:
            raise AuthorizationError("No deletion request pending for this task")

        if approver_id == task.deletion_requested_by:
            raise AuthorizationError("Cannot approve your own deletion request")

        await self._session.delete(task)
        await self._session.commit()

    async def list_tasks(self, member_id: int | None = None) -> list[Task]:
        """List tasks, respecting visibility rules when scoped to a member."""
        if member_id is not None:
            stmt = select(Task).where(
                (Task.visibility == TaskVisibility.SHARED)
                | (Task.assignee_id == member_id)
            )
        else:
            stmt = select(Task)
        result = await self._session.exec(stmt)
        return list(result.all())

    async def get_overdue(self) -> list[Task]:
        """Return tasks past their deadline that are not yet verified."""
        now = datetime.now(UTC)
        stmt = select(Task).where(
            Task.status != TaskStatus.VERIFIED,
            col(Task.deadline).isnot(None),
            col(Task.deadline) < now,
        )
        result = await self._session.exec(stmt)
        return list(result.all())

    async def get_stats(self, member_id: int) -> dict:
        """Return completion count and rank for a member."""
        # Count completions for the target member
        count_result = await self._session.exec(
            select(func.count())
            .select_from(CompletionHistory)
            .where(CompletionHistory.completed_by_id == member_id)
        )
        completion_count: int = count_result.one()

        # Get all members' counts for ranking
        leaderboard = await self.get_leaderboard()
        rank = 1
        for entry in leaderboard:
            if entry["member_id"] == member_id:
                rank = entry["rank"]
                break

        return {
            "member_id": member_id,
            "completion_count": completion_count,
            "rank": rank,
        }

    async def get_leaderboard(self) -> list[dict]:
        """Return leaderboard sorted by count desc, tie-break by ID."""
        stmt = (
            select(
                CompletionHistory.completed_by_id,
                func.count().label("completion_count"),
            )
            .group_by(CompletionHistory.completed_by_id)
            .order_by(
                func.count().desc(),
                CompletionHistory.completed_by_id.asc(),  # type: ignore[union-attr]
            )
        )
        result = await self._session.exec(stmt)
        rows = result.all()

        leaderboard: list[dict] = []
        for rank, row in enumerate(rows, start=1):
            leaderboard.append(
                {
                    "rank": rank,
                    "member_id": row[0],
                    "completion_count": row[1],
                }
            )
        return leaderboard

    async def count_weekly_takeovers(self, member_id: int) -> int:
        """Count completions this week where the completer is not the task assignee."""
        now = datetime.now(UTC)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        stmt = (
            select(func.count())
            .select_from(CompletionHistory)
            .join(Task, CompletionHistory.task_id == Task.id)
            .where(
                CompletionHistory.completed_by_id == member_id,
                CompletionHistory.completed_by_id != Task.assignee_id,
                col(CompletionHistory.completed_at) >= week_start,
            )
        )
        result = await self._session.exec(stmt)
        return result.one()

    def _handle_recurrence_reset(self, task: Task) -> None:
        """Reset a recurring task to PENDING with the next scheduled deadline."""
        if task.recurrence is None:
            return

        if task.next_deadline is not None:
            task.next_deadline = _calculate_next_deadline(
                task.next_deadline, task.recurrence
            )
        elif task.deadline is not None:
            task.next_deadline = _calculate_next_deadline(
                task.deadline, task.recurrence
            )

        task.deadline = task.next_deadline
        task.status = TaskStatus.PENDING
