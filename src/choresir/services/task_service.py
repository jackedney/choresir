"""Task lifecycle: creation, completion, verification, recurrence."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from choresir.enums import TaskStatus, TaskVisibility, VerificationMode
from choresir.errors import (
    AuthorizationError,
    InvalidTransitionError,
    NotFoundError,
    TakeoverLimitExceededError,
)
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


def _next_deadline(current: datetime, recurrence: str) -> datetime:
    """Advance deadline by the recurrence interval."""
    match recurrence:
        case "daily":
            return current + timedelta(days=1)
        case "weekly":
            return current + timedelta(weeks=1)
        case "monthly":
            y = current.year + (current.month // 12)
            m = (current.month % 12) + 1
            d = min(current.day, calendar.monthrange(y, m)[1])
            return current.replace(year=y, month=m, day=d)
        case _:
            raise ValueError(f"Unsupported recurrence: {recurrence}")


class TaskService:
    """Task lifecycle: creation, completion, verification."""

    def __init__(self, session: AsyncSession, max_takeovers_per_week: int) -> None:
        self._session = session
        self._max_takeovers_per_week = max_takeovers_per_week

    async def _pending_history(self, task_id: int) -> CompletionHistory | None:
        """Return the latest unverified completion history entry."""
        result = await self._session.exec(
            select(CompletionHistory)
            .where(
                CompletionHistory.task_id == task_id,
                col(CompletionHistory.verified_at).is_(None),
            )
            .order_by(col(CompletionHistory.completed_at).desc())
        )
        return result.first()

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
        """Claim completion. Skips to VERIFIED if no verification needed."""
        task = await self.get_task(task_id)

        if member_id != task.assignee_id:
            takeover_count = await self.count_weekly_takeovers(member_id)
            if takeover_count >= self._max_takeovers_per_week:
                raise TakeoverLimitExceededError(self._max_takeovers_per_week)

        now = datetime.now(UTC)
        if task.verification_mode == VerificationMode.NONE:
            transition_task(task, TaskStatus.CLAIMED)
            transition_task(task, TaskStatus.VERIFIED)
            self._session.add(
                CompletionHistory(
                    task_id=task.id,  # type: ignore[arg-type]
                    completed_by_id=member_id,
                    completed_at=now,
                    verified_at=now,
                )
            )
            self._handle_recurrence_reset(task)
        else:
            transition_task(task, TaskStatus.CLAIMED)
            self._session.add(
                CompletionHistory(
                    task_id=task.id,  # type: ignore[arg-type]
                    completed_by_id=member_id,
                    completed_at=now,
                )
            )
        task.updated_at = now
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

        pending = await self._pending_history(task_id)
        claimant_id = pending.completed_by_id if pending else None

        if verifier_id == claimant_id:
            raise AuthorizationError("Cannot verify your own completion claim")
        if (
            task.verification_mode == VerificationMode.PARTNER
            and verifier_id != task.partner_id
        ):
            raise AuthorizationError("Only the designated partner can verify this task")

        transition_task(task, TaskStatus.VERIFIED)
        now = datetime.now(UTC)
        if pending:
            pending.verified_by_id = verifier_id
            pending.verified_at = now
            pending.feedback = feedback
            self._session.add(pending)
        else:
            self._session.add(
                CompletionHistory(
                    task_id=task.id,  # type: ignore[arg-type]
                    completed_by_id=task.assignee_id,
                    verified_by_id=verifier_id,
                    feedback=feedback,
                    completed_at=now,
                    verified_at=now,
                )
            )
        self._handle_recurrence_reset(task)
        task.updated_at = now
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def reject_completion(self, task_id: int, verifier_id: int) -> Task:
        """Reject a completion claim, returning task to PENDING."""
        task = await self.get_task(task_id)
        if task.status != TaskStatus.CLAIMED:
            raise InvalidTransitionError(task.status, TaskStatus.PENDING)

        pending = await self._pending_history(task_id)
        claimant_id = pending.completed_by_id if pending else None
        if verifier_id == claimant_id:
            raise AuthorizationError("Cannot reject your own completion claim")

        transition_task(task, TaskStatus.PENDING)
        if pending:
            await self._session.delete(pending)
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
        """Approve and delete. Approver must differ from requester."""
        task = await self.get_task(task_id)
        if task.deletion_requested_by is None:
            raise AuthorizationError("No deletion request pending")
        if approver_id == task.deletion_requested_by:
            raise AuthorizationError("Cannot approve your own deletion request")
        await self._session.delete(task)
        await self._session.commit()

    async def list_tasks(self, member_id: int | None = None) -> list[Task]:
        """List tasks, respecting visibility for a given member."""
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
        """Return tasks past deadline that are not yet verified."""
        now = datetime.now(UTC)
        stmt = select(Task).where(
            Task.status != TaskStatus.VERIFIED,
            col(Task.deadline).isnot(None),
            col(Task.deadline) < now,
        )
        result = await self._session.exec(stmt)
        return list(result.all())

    async def get_upcoming(self, hours: int = 24) -> list[Task]:
        """Return tasks with deadlines in the next N hours that are not yet verified."""
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=hours)
        stmt = (
            select(Task)
            .where(
                Task.status != TaskStatus.VERIFIED,
                col(Task.deadline).isnot(None),
                col(Task.deadline) >= now,
                col(Task.deadline) <= cutoff,
            )
            .order_by(col(Task.deadline).asc())
        )
        result = await self._session.exec(stmt)
        return list(result.all())

    async def get_stats(self, member_id: int) -> dict:
        """Return completion count and rank for a member."""
        count_result = await self._session.exec(
            select(func.count())
            .select_from(CompletionHistory)
            .where(CompletionHistory.completed_by_id == member_id)
        )
        completion_count: int = count_result.one()
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
        return [
            {"rank": i, "member_id": r[0], "completion_count": r[1]}
            for i, r in enumerate(result.all(), start=1)
        ]

    async def count_weekly_takeovers(self, member_id: int) -> int:
        """Count completions this week where completer != assignee."""
        now = datetime.now(UTC)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
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
        """Reset a recurring task to PENDING with next deadline."""
        if task.recurrence is None:
            return
        anchor = task.next_deadline or task.deadline
        if anchor is not None:
            task.next_deadline = _next_deadline(anchor, task.recurrence)
        task.deadline = task.next_deadline
        task.status = TaskStatus.PENDING
