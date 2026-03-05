"""Integration tests for agent tool execution."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from choresir.agent.agent import AgentDeps, create_agent
from choresir.agent.tools.tasks import create_task, list_tasks
from choresir.agent.tools.verification import complete_task
from choresir.config import Settings
from choresir.services.member_service import MemberService
from choresir.services.task_service import TaskService


@pytest.fixture
def settings():
    return Settings(llm_model="test")


@pytest.fixture
def test_model():
    return TestModel()


@pytest.fixture
def test_usage():
    return RunUsage()


@pytest.mark.anyio
async def test_agent_has_all_tools_registered(settings):
    agent = create_agent(settings)
    tool_names = list(agent._function_toolset.tools.keys())

    expected_tools = [
        "create_task",
        "reassign_task",
        "delete_task",
        "approve_deletion",
        "list_tasks",
        "complete_task",
        "verify_completion",
        "reject_completion",
        "get_stats",
        "get_leaderboard",
        "get_overdue_tasks",
    ]

    for expected in expected_tools:
        assert expected in tool_names, f"Tool {expected} not registered"


@pytest.mark.anyio
async def test_create_task_success(session, test_model, test_usage):
    member_svc = MemberService(session)
    member = await member_svc.register_pending("test@c.us")
    member = await member_svc.activate("test@c.us", "Test User")

    task_svc = TaskService(session)
    deps = AgentDeps(task_service=task_svc, member_service=member_svc)
    ctx = RunContext(
        deps=deps,
        model=test_model,
        usage=test_usage,
        retry=0,
        messages=[],
        tool_name="create_task",
    )

    result = await create_task(
        ctx,
        title="Test task",
        assignee_id=member.id,
    )

    assert "Test task" in result
    assert "created" in result


@pytest.mark.anyio
async def test_complete_task_success(session, test_model, test_usage):
    member_svc = MemberService(session)
    member = await member_svc.register_pending("test@c.us")
    member = await member_svc.activate("test@c.us", "Test User")

    task_svc = TaskService(session)

    task = await task_svc.create_task(
        title="Task to complete",
        assignee_id=member.id,
    )
    await session.commit()

    deps = AgentDeps(task_service=task_svc, member_service=member_svc)
    ctx = RunContext(
        deps=deps,
        model=test_model,
        usage=test_usage,
        retry=0,
        messages=[],
        tool_name="complete_task",
    )

    result = await complete_task(ctx, task_id=task.id, member_id=member.id)

    assert "Task to complete" in result
    assert "completed" in result or "awaiting verification" in result


@pytest.mark.anyio
async def test_complete_task_not_found(session, test_model, test_usage):
    member_svc = MemberService(session)
    member = await member_svc.register_pending("test@c.us")
    member = await member_svc.activate("test@c.us", "Test User")

    task_svc = TaskService(session)
    deps = AgentDeps(task_service=task_svc, member_service=member_svc)
    ctx = RunContext(
        deps=deps,
        model=test_model,
        usage=test_usage,
        retry=0,
        messages=[],
        tool_name="complete_task",
    )

    result = await complete_task(ctx, task_id=999, member_id=member.id)

    assert "not found" in result.lower()


@pytest.mark.anyio
async def test_list_tasks_empty(session, test_model, test_usage):
    task_svc = TaskService(session)
    member_svc = MemberService(session)
    deps = AgentDeps(task_service=task_svc, member_service=member_svc)
    ctx = RunContext(
        deps=deps,
        model=test_model,
        usage=test_usage,
        retry=0,
        messages=[],
        tool_name="list_tasks",
    )

    result = await list_tasks(ctx)

    assert result == "No tasks found."


@pytest.mark.anyio
async def test_list_tasks_with_tasks(session, test_model, test_usage):
    member_svc = MemberService(session)
    member = await member_svc.register_pending("test@c.us")
    member = await member_svc.activate("test@c.us", "Test User")

    task_svc = TaskService(session)

    await task_svc.create_task(title="Task 1", assignee_id=member.id)
    await task_svc.create_task(title="Task 2", assignee_id=member.id)
    await session.commit()

    deps = AgentDeps(task_service=task_svc, member_service=member_svc)
    ctx = RunContext(
        deps=deps,
        model=test_model,
        usage=test_usage,
        retry=0,
        messages=[],
        tool_name="list_tasks",
    )

    result = await list_tasks(ctx)

    assert "Task 1" in result
    assert "Task 2" in result
    assert "[pending]" in result
