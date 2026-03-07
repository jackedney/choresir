"""Tests for MemberService and TaskService with in-memory DB."""

from __future__ import annotations

import pytest

from choresir.enums import (
    MemberStatus,
    TaskStatus,
    VerificationMode,
)
from choresir.errors import (
    AuthorizationError,
    InvalidTransitionError,
    NotFoundError,
)
from choresir.services.member_service import MemberService
from choresir.services.task_service import TaskService
from tests.conftest import make_member


class TestMemberService:
    @pytest.mark.anyio
    async def test_register_pending_creates_pending_member(self, session):
        svc = MemberService(session)
        member = await svc.register_pending("new@c.us")
        assert member.whatsapp_id == "new@c.us"
        assert member.status == MemberStatus.PENDING

    @pytest.mark.anyio
    async def test_activate_sets_name_and_status(self, session):
        svc = MemberService(session)
        await svc.register_pending("user@c.us")
        member = await svc.activate("user@c.us", "Alice")
        assert member.name == "Alice"
        assert member.status == MemberStatus.ACTIVE

    @pytest.mark.anyio
    async def test_get_active_raises_on_pending(self, session):
        svc = MemberService(session)
        pending = await svc.register_pending("pending@c.us")
        with pytest.raises(AuthorizationError):
            await svc.get_active(pending.id)

    @pytest.mark.anyio
    async def test_list_active_filters_pending(self, session):
        svc = MemberService(session)
        await svc.register_pending("pending@c.us")
        await svc.register_pending("active@c.us")
        await svc.activate("active@c.us", "Active User")

        active = await svc.list_active()
        assert len(active) == 1
        assert active[0].whatsapp_id == "active@c.us"

    @pytest.mark.anyio
    async def test_get_by_whatsapp_id_not_found(self, session):
        svc = MemberService(session)
        with pytest.raises(NotFoundError):
            await svc.get_by_whatsapp_id("nonexistent@c.us")


class TestTaskService:
    async def _create_active_member(self, session, whatsapp_id="member@c.us"):
        member = make_member(whatsapp_id=whatsapp_id, status=MemberStatus.ACTIVE)
        session.add(member)
        await session.commit()
        await session.refresh(member)
        return member

    @pytest.mark.anyio
    async def test_create_task(self, session, fake_sender):
        member = await self._create_active_member(session)
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Wash dishes",
            assignee_id=member.id,
        )
        assert task.title == "Wash dishes"
        assert task.status == TaskStatus.PENDING
        assert task.id is not None

    @pytest.mark.anyio
    async def test_claim_completion_none_mode_goes_to_verified(
        self, session, fake_sender
    ):
        member = await self._create_active_member(session)
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Quick task",
            assignee_id=member.id,
            verification_mode=VerificationMode.NONE,
        )
        result = await svc.claim_completion(task.id, member.id)
        assert result.status == TaskStatus.VERIFIED

    @pytest.mark.anyio
    async def test_claim_completion_peer_mode_stays_claimed(self, session, fake_sender):
        member = await self._create_active_member(session)
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Peer task",
            assignee_id=member.id,
            verification_mode=VerificationMode.PEER,
        )
        result = await svc.claim_completion(task.id, member.id)
        assert result.status == TaskStatus.CLAIMED

    @pytest.mark.anyio
    async def test_verify_completion(self, session, fake_sender):
        member = await self._create_active_member(session)
        verifier = await self._create_active_member(session, "verifier@c.us")
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Verified task",
            assignee_id=member.id,
            verification_mode=VerificationMode.PEER,
        )
        await svc.claim_completion(task.id, member.id)
        result = await svc.verify_completion(task.id, verifier.id)
        assert result.status == TaskStatus.VERIFIED

    @pytest.mark.anyio
    async def test_self_verification_raises(self, session, fake_sender):
        member = await self._create_active_member(session)
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Self-verify attempt",
            assignee_id=member.id,
            verification_mode=VerificationMode.PEER,
        )
        await svc.claim_completion(task.id, member.id)
        with pytest.raises(AuthorizationError, match="Cannot verify your own"):
            await svc.verify_completion(task.id, member.id)

    @pytest.mark.anyio
    async def test_reject_completion(self, session, fake_sender):
        member = await self._create_active_member(session)
        verifier = await self._create_active_member(session, "verifier@c.us")
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Reject me",
            assignee_id=member.id,
            verification_mode=VerificationMode.PEER,
        )
        await svc.claim_completion(task.id, member.id)
        result = await svc.reject_completion(task.id, verifier.id)
        assert result.status == TaskStatus.PENDING

    @pytest.mark.anyio
    async def test_reassign(self, session, fake_sender):
        member = await self._create_active_member(session)
        new_member = await self._create_active_member(session, "new@c.us")
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Reassign me",
            assignee_id=member.id,
        )
        result = await svc.reassign(task.id, new_member.id)
        assert result.assignee_id == new_member.id

    @pytest.mark.anyio
    async def test_get_task_not_found(self, session, fake_sender):
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        with pytest.raises(NotFoundError):
            await svc.get_task(9999)

    @pytest.mark.anyio
    async def test_claim_completion_non_assignee_non_pending_fails_early(
        self, session, fake_sender
    ):
        assignee = await self._create_active_member(session, "assignee@c.us")
        other = await self._create_active_member(session, "other@c.us")
        svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
        task = await svc.create_task(
            title="Already claimed",
            assignee_id=assignee.id,  # type: ignore[arg-type]
            verification_mode=VerificationMode.PEER,
        )
        await svc.claim_completion(task.id, assignee.id)  # type: ignore[arg-type]
        with pytest.raises(InvalidTransitionError):
            await svc.claim_completion(task.id, other.id)  # type: ignore[arg-type]
