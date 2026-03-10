"""Property-based tests for domain invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from choresir.enums import TaskStatus, VerificationMode
from choresir.errors import AuthorizationError
from choresir.services.task_service import TaskService
from tests.conftest import make_member


class TestNoSelfVerification:
    """Invariant 2: completed_by_id != verified_by_id always."""

    @pytest.mark.anyio
    async def test_member_cannot_verify_own_claimed_task(
        self, session: AsyncSession, fake_sender
    ) -> None:
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        member = make_member(whatsapp_id="member@c.us", name="Member")
        session.add(member)
        await session.commit()
        await session.refresh(member)
        assert member.id is not None

        task = await svc.create_task(
            title="Test task",
            assignee_id=member.id,
            verification_mode=VerificationMode.PEER,
        )
        assert task.id is not None
        await svc.claim_completion(task.id, member.id)

        with pytest.raises(AuthorizationError, match="Cannot verify your own"):
            await svc.verify_completion(task.id, member.id)

    @pytest.mark.anyio
    async def test_member_cannot_reject_own_claimed_task(
        self, session: AsyncSession, fake_sender
    ) -> None:
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        member = make_member(whatsapp_id="member@c.us", name="Member")
        session.add(member)
        await session.commit()
        await session.refresh(member)
        assert member.id is not None

        task = await svc.create_task(
            title="Test task",
            assignee_id=member.id,
            verification_mode=VerificationMode.PEER,
        )
        assert task.id is not None
        await svc.claim_completion(task.id, member.id)

        with pytest.raises(AuthorizationError, match="Cannot reject your own"):
            await svc.reject_completion(task.id, member.id)


class TestNoVerificationSkipsClaimed:
    """Invariant 3: Tasks with verification_mode=NONE skip CLAIMED state."""

    @pytest.mark.anyio
    async def test_none_verification_task_goes_straight_to_verified(
        self, session: AsyncSession, fake_sender
    ) -> None:
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        member = make_member(whatsapp_id="member@c.us", name="Member")
        session.add(member)
        await session.commit()
        await session.refresh(member)
        assert member.id is not None

        task = await svc.create_task(
            title="Test task",
            assignee_id=member.id,
            verification_mode=VerificationMode.NONE,
        )
        assert task.id is not None
        assert task.status == TaskStatus.PENDING

        updated = await svc.claim_completion(task.id, member.id)
        assert updated.status == TaskStatus.VERIFIED


class TestRecurringTaskNextDeadline:
    """Invariant 4: Recurring verified tasks have next_deadline in future or None."""

    @pytest.mark.anyio
    async def test_verified_recurring_task_has_future_next_deadline(
        self, session: AsyncSession, fake_sender
    ) -> None:
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        member = make_member(whatsapp_id="member@c.us", name="Member")
        session.add(member)
        await session.commit()
        await session.refresh(member)
        assert member.id is not None

        now = datetime.now(UTC)
        deadline = now + timedelta(days=1)

        task = await svc.create_task(
            title="Daily task",
            assignee_id=member.id,
            verification_mode=VerificationMode.NONE,
            recurrence="daily",
            deadline=deadline,
        )
        assert task.id is not None
        assert task.status == TaskStatus.PENDING

        updated = await svc.claim_completion(task.id, member.id)
        await session.refresh(updated)

        assert updated.status == TaskStatus.PENDING
        assert updated.next_deadline is not None
        if updated.next_deadline.tzinfo is None:
            assert updated.next_deadline.replace(tzinfo=UTC) > now
        else:
            assert updated.next_deadline > now

    @pytest.mark.anyio
    async def test_recurring_task_without_deadline_has_none_or_future_next_deadline(
        self, session: AsyncSession, fake_sender
    ) -> None:
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        member = make_member(whatsapp_id="member@c.us", name="Member")
        session.add(member)
        await session.commit()
        await session.refresh(member)
        assert member.id is not None

        task = await svc.create_task(
            title="Recurring without deadline",
            assignee_id=member.id,
            verification_mode=VerificationMode.NONE,
            recurrence="daily",
            deadline=None,
        )
        assert task.id is not None

        updated = await svc.claim_completion(task.id, member.id)
        now = datetime.now(UTC)

        if updated.next_deadline is not None:
            if updated.next_deadline.tzinfo is None:
                assert updated.next_deadline.replace(tzinfo=UTC) > now
            else:
                assert updated.next_deadline > now
