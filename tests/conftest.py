"""Shared test fixtures."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Ensure all table models are imported so metadata.create_all sees them.
import choresir.models.job  # noqa: F401
from choresir.enums import (
    MemberRole,
    MemberStatus,
    TaskStatus,
    TaskVisibility,
    VerificationMode,
)
from choresir.models.member import Member
from choresir.models.task import Task


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def fake_sender():
    class FakeSender:
        def __init__(self):
            self.sent: list[tuple[str, str]] = []

        async def send(self, chat_id: str, text: str) -> None:
            self.sent.append((chat_id, text))

    return FakeSender()


def make_member(
    whatsapp_id: str = "test@c.us",
    name: str = "Test User",
    role: MemberRole = MemberRole.MEMBER,
    status: MemberStatus = MemberStatus.ACTIVE,
    **overrides,
) -> Member:
    return Member(
        whatsapp_id=whatsapp_id, name=name, role=role, status=status, **overrides
    )


def make_task(
    title: str = "Test task",
    status: TaskStatus = TaskStatus.PENDING,
    assignee_id: int = 1,
    verification_mode: VerificationMode = VerificationMode.NONE,
    visibility: TaskVisibility = TaskVisibility.SHARED,
    **overrides,
) -> Task:
    return Task(
        title=title,
        status=status,
        assignee_id=assignee_id,
        verification_mode=verification_mode,
        visibility=visibility,
        **overrides,
    )


@pytest.fixture
async def agent_deps(session, fake_sender):
    from choresir.agent.agent import AgentDeps
    from choresir.services.member_service import MemberService
    from choresir.services.task_service import TaskService

    task_service = TaskService(session, fake_sender, max_takeovers_per_week=3)
    member_service = MemberService(session)
    return AgentDeps(
        task_service=task_service,
        member_service=member_service,
        sender_id="test@c.us",
    )
