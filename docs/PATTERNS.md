# Implementation Patterns

## Code Organization

Domain-centric module structure where `services/` is the core and all boundary layers (agent, webhook, worker, scheduler, admin) call into it.

```
src/choresir/
├── __init__.py
├── app.py                  # FastAPI app factory, lifespan, mount admin
├── config.py               # Settings via pydantic-settings, enums for config values
├── models/                 # SQLModel table definitions (pure data, no logic)
│   ├── __init__.py
│   ├── task.py             # Task, CompletionHistory
│   ├── member.py           # Member
│   └── job.py              # MessageJob (queue)
├── enums.py                # TaskStatus, VerificationMode, MemberRole, MemberStatus, TaskVisibility, JobStatus
├── errors.py               # Exception hierarchy
├── webhook/                # Inbound webhook handling
│   ├── __init__.py
│   ├── router.py           # FastAPI router, signature validation, group.v2.join handling
│   └── auth.py             # Webhook authenticity checks
├── worker/                 # Message processing pipeline
│   ├── __init__.py
│   ├── queue.py            # Job queue operations (claim, complete, retry, fail)
│   └── processor.py        # Worker loop, rate limiting, retry logic
├── agent/                  # PydanticAI agent layer
│   ├── __init__.py
│   ├── agent.py            # Agent definition, AgentDeps dataclass, system prompt assembly
│   ├── registry.py         # Tool registry
│   ├── tools/              # Tool functions grouped by domain
│   │   ├── __init__.py
│   │   ├── tasks.py        # create_task, reassign_task, delete_task, approve_deletion, list_tasks
│   │   ├── verification.py # verify_completion, reject_completion
│   │   ├── analytics.py    # stats, leaderboard queries
│   │   └── onboarding.py   # register_member, set_name
│   └── prompts/            # System prompt templates (plain text files)
│       └── base.txt
├── scheduler/              # APScheduler jobs
│   ├── __init__.py
│   ├── setup.py            # Scheduler configuration, job registration
│   └── jobs.py             # Individual job functions (+ _NullSender)
├── admin/                  # FastHTML admin interface
│   ├── __init__.py
│   ├── app.py              # FastHTML app, auth, CSRF
│   └── pages.py            # Page handlers
├── services/               # Shared domain logic (composed, not inherited)
│   ├── __init__.py
│   ├── task_service.py     # Task CRUD, verification, recurrence logic
│   ├── member_service.py   # Member registration, onboarding
│   └── messaging.py        # MessageSender protocol, WAHAClient
└── db.py                   # Engine/session factory, async session context
```

### Naming Conventions

- **Modules**: lowercase snake_case, singular nouns for models (`task.py`), plural for tool groups (`tasks.py` in tools/)
- **Classes**: PascalCase, matching domain nouns (`Task`, `Member`, `MessageJob`)
- **Enums**: PascalCase class, UPPER_SNAKE members (`class VerificationMode(str, Enum): NONE = "none"`)
- **Functions**: snake_case, service methods are verbs (`create_task`, `verify_completion`)
- **Constants**: UPPER_SNAKE in `config.py`

### Structural Principles

- **`services/` as the domain core** — all business logic lives here. Agent tools, scheduler jobs, and admin pages call into services. No duplicated logic at the edges.
- **`models/` separate from `services/`** — models are pure data definitions (SQLModel tables + enums). No business logic in model classes.
- **`agent/tools/` grouped by domain** — tools split by responsibility, self-registering via the registry pattern.
- **AgentDeps as dependency container** — PydanticAI uses a typed dataclass for runtime deps. Services, sender ID, and request context flow through `RunContext[AgentDeps]`. Tools access via `ctx.deps`.
- **Flat where small, nested where justified** — `webhook/` and `worker/` can start as single files; the directory structure accommodates growth without reorganization.

## Design Patterns

### Protocol-Based Service Interfaces

Define protocols for key boundaries so components depend on abstractions. This makes testing trivial — swap in a fake that satisfies the protocol.

```python
from typing import Protocol

class MessageSender(Protocol):
    async def send(self, chat_id: str, text: str) -> None: ...

class WAHAClient:
    """Production implementation."""
    def __init__(self, base_url: str, api_key: str, session: str, http: httpx.AsyncClient) -> None: ...

    async def send(self, chat_id: str, text: str) -> None: ...
```

Services accept `MessageSender`, never `WAHAClient` directly. Tests pass a `FakeSender` that records calls.

### Registry Pattern for Agent Tools

Tools self-register via a registry, keeping the agent definition clean and tool groups decoupled:

```python
# agent/registry.py
@dataclass
class ToolRegistry:
    _tools: list[Callable] = field(default_factory=list)

    def register(self, fn: Callable) -> Callable:
        self._tools.append(fn)
        return fn

    def apply[D, R](self, agent: Agent[D, R]) -> None:
        for tool_fn in self._tools:
            agent.tool(tool_fn)

registry = ToolRegistry()

# agent/tools/tasks.py
@registry.register
async def create_task(ctx: RunContext[AgentDeps], title: str, ...) -> str: ...

# agent/agent.py
registry.apply(agent)
```

Adding a new tool = writing a decorated function in the right file. No imports to update in the agent module.

### Composition-Based Services

Services compose dependencies via `__init__`, never inherit from a base service:

```python
class TaskService:
    def __init__(self, session: AsyncSession, sender: MessageSender, max_takeovers_per_week: int) -> None: ...

    async def create_task(self, ...) -> Task: ...
```

### Enum-Driven State Machines

Task lifecycle, member onboarding, and job processing use enums, never raw strings. State transitions are validated:

```python
class TaskStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    VERIFIED = "verified"

_VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.CLAIMED}),
    TaskStatus.CLAIMED: frozenset({TaskStatus.PENDING, TaskStatus.VERIFIED}),
}

def transition_task(task: Task, to: TaskStatus) -> None:
    if to not in _VALID_TRANSITIONS.get(task.status, frozenset()):
        raise InvalidTransitionError(task.status, to)
    task.status = to
```

Member onboarding follows the same pattern:

```python
class MemberStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"

_MEMBER_TRANSITIONS: dict[MemberStatus, frozenset[MemberStatus]] = {
    MemberStatus.PENDING: frozenset({MemberStatus.ACTIVE}),
    MemberStatus.ACTIVE: frozenset(),  # terminal state
}

def transition_member(member: Member, to: MemberStatus) -> None: ...
```

`TaskVisibility` is immutable at task creation, not a state machine.

This applies equally to `JobStatus`, `MemberRole`, and `VerificationMode`.

### AgentDeps + RunContext Pattern

PydanticAI tools receive a typed context object, not individual services:

```python
@dataclass
class AgentDeps:
    task_service: TaskService
    member_service: MemberService
    sender_id: str

@registry.register
async def create_task(ctx: RunContext[AgentDeps], title: str, assignee_id: int) -> str:
    await ctx.deps.task_service.create_task(...)
```

Tools call `ctx.deps.task_service` and `ctx.deps.member_service`. This isolates tool functions from service wiring changes.

### Dynamic System Prompt

Base template loaded from disk, household context assembled from DB per request via decorator:

```python
_PROMPT = (Path(__file__).parent / "prompts" / "base.txt").read_text()

@agent.system_prompt
async def _household_ctx(ctx: RunContext[AgentDeps]) -> str:
    members = await ctx.deps.member_service.list_active()
    tasks = await ctx.deps.task_service.list_tasks()
    today = date.today()
    parts = [
        f"Today's date: {today.strftime('%A, %B %-d, %Y')}",
        f"Sender WhatsApp ID: {ctx.deps.sender_id}",
    ]
    if members:
        lines = [f"- {m.name} (ID {m.id})" for m in members]
        parts.append("Active members:\n" + "\n".join(lines))
    if tasks:
        lines = [f"- [{t.status.value}] {t.title} (ID {t.id})" for t in tasks]
        parts.append("Current tasks:\n" + "\n".join(lines))
    return "\n\n".join(parts) if parts else ""
```

The decorator runs before each agent call, injecting current members, tasks, and date.

### Retry Wrapper for AI Calls

Tenacity handles transient LLM failures at the call site, not inside services:

```python
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((TimeoutError, httpx.RequestError)),
    reraise=True,
)
async def call_agent_with_retry(agent, message: str, deps: AgentDeps) -> str:
    result = await agent.run(message, deps=deps)
    return result.output
```

Services remain unaware of retry logic. The worker loop catches final failures and marks jobs as failed.

### Null Object for Non-Messaging Jobs

Scheduler jobs that don't send messages use a no-op sender:

```python
class _NullSender:
    async def send(self, chat_id: str, text: str) -> None: ...
```

This avoids branching on `sender is None` in `TaskService`.

### Dependency Assembly via App Factory

The FastAPI app factory wires everything together — no global mutable state:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_async_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    http_client = httpx.AsyncClient()
    sender = WAHAClient(settings.waha_url, settings.waha_api_key, "default", http_client)
    # ... wire into routers, agent, scheduler
    return app
```

Tests call `create_app(test_settings)` with an in-memory DB and fake sender.

## Error Handling

### Exception Hierarchy

A typed exception tree rooted in a single base. Each exception carries structured context, not just a message string:

```python
# errors.py

class ChoresirError(Exception):
    """Base for all domain errors."""

class InvalidTransitionError(ChoresirError):
    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from {current} to {target}")

class NotFoundError(ChoresirError):
    def __init__(self, entity: str, identifier: str | int) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier}")

class AuthorizationError(ChoresirError):
    """Member lacks permission for the operation (e.g., self-verification)."""

class TakeoverLimitExceededError(ChoresirError):
    """Weekly takeover limit exceeded."""
    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"Weekly takeover limit of {limit} exceeded")

class RateLimitExceededError(ChoresirError):
    """Per-user or global rate limit hit."""

class WebhookAuthError(ChoresirError):
    """Invalid webhook signature."""
```

### Error Flow by Layer

| Layer | Raises | Catches |
|-------|--------|---------|
| **Services** | Domain errors (`InvalidTransitionError`, `NotFoundError`, `AuthorizationError`, `TakeoverLimitExceededError`) | Nothing — let errors propagate |
| **Agent tools** | Nothing new | Catches domain errors, returns user-friendly strings to the LLM |
| **Webhook router** | `WebhookAuthError` | Nothing — handled by exception handler |
| **Worker/processor** | Nothing new | Catches all errors for retry/fail decisions |
| **FastAPI exception handlers** | — | Maps `WebhookAuthError` to 401, `RateLimitExceededError` to 429 |

### Agent Tool Error Handling

Tools define a tuple of caught domain errors and return their string representation:

```python
_DOMAIN_ERRORS = (NotFoundError, AuthorizationError)

@registry.register
async def create_task(ctx: RunContext[AgentDeps], title: str, assignee_id: int) -> str:
    try:
        await _ensure_active_member(ctx, assignee_id)
        task = await ctx.deps.task_service.create_task(...)
        return f"Task '{task.title}' (ID {task.id}) created."
    except (*_DOMAIN_ERRORS, ValueError) as e:
        return str(e)
```

Tools that perform takeovers also catch `TakeoverLimitExceededError`. The pattern is consistent: catch specific domain errors, return their string representation so the LLM can communicate naturally.

### Principles

- **Services raise, boundaries catch.** Domain logic never silences errors. Translation to HTTP responses or LLM-friendly messages happens at the edges.
- **Agent tools return strings, never raise.** A tool that raises kills the agent run. Catch domain errors and return descriptive text so the LLM can communicate the problem naturally.
- **Structured logging at catch sites.** Log with structured context (task ID, member ID, error type), not string-interpolated tracebacks.
- **Retry decisions in the worker only.** The worker catches exceptions from the agent layer and decides: transient failure (LLM timeout) leads to retry with backoff via `run_after`; permanent failure (max attempts) leads to marking `failed` and logging.
- **No bare `except`.** Always catch specific types. The only broad catch is `except Exception` in the worker loop (to prevent a single message from crashing the process), and it logs the full traceback before marking the job failed.

## Testing Patterns

### Structure

```
tests/
├── conftest.py             # Shared fixtures: async engine, session, fake sender, agent_deps
├── unit/                   # Pure logic, no I/O
│   ├── test_transitions.py # State machine validation (TaskStatus, MemberStatus)
│   ├── test_enums.py       # Enum completeness
│   └── test_services.py    # Services with in-memory DB + fakes
├── integration/            # Real DB, real app, mocked externals
│   ├── test_webhook.py     # Webhook auth, dedup, rate limiting
│   ├── test_worker.py      # Job claiming, retry, failure
│   └── test_agent.py       # Agent tool execution with mock LLM
└── conftest_fixtures/      # Complex fixture helpers if conftest.py grows
```

### Fixtures

In-memory SQLite for speed. Services get real sessions but fake externals:

```python
# conftest.py
import pytest
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()

@pytest.fixture
async def session(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        yield s

@pytest.fixture
def fake_sender():
    class FakeSender:
        def __init__(self):
            self.sent: list[tuple[str, str]] = []
        async def send(self, chat_id: str, text: str) -> None:
            self.sent.append((chat_id, text))
    return FakeSender()

@pytest.fixture
def agent_deps(session, fake_sender):
    return AgentDeps(
        task_service=TaskService(session, fake_sender, max_takeovers_per_week=3),
        member_service=MemberService(session),
        sender_id="test_sender",
    )
```

### Testing Agent Tools with AgentDeps

Build deps with real services and fake externals, then construct a RunContext:

```python
@pytest.mark.anyio
async def test_create_task_success(agent_deps):
    ctx = RunContext(deps=agent_deps, retry=0, messages=[])
    result = await create_task(ctx, title="Dishes", assignee_id=1)
    assert "created" in result.lower()
```

### Testing State Machines

Hypothesis for domain invariants. Add MemberStatus to coverage:

```python
from hypothesis import given, strategies as st

@given(st.sampled_from(TaskStatus), st.sampled_from(TaskStatus))
def test_invalid_task_transitions_raise(current, target):
    if target not in _VALID_TRANSITIONS.get(current, frozenset()):
        task = make_task(status=current)
        with pytest.raises(InvalidTransitionError):
            transition_task(task, target)

@given(st.sampled_from(MemberStatus), st.sampled_from(MemberStatus))
def test_invalid_member_transitions_raise(current, target):
    if target not in _MEMBER_TRANSITIONS.get(current, frozenset()):
        member = make_member(status=current)
        with pytest.raises(InvalidTransitionError):
            transition_member(member, target)
```

### Testing Task Visibility

Verify personal tasks are hidden from non-owners:

```python
@pytest.mark.anyio
async def test_list_tasks_hides_personal_from_non_owner(session, fake_sender):
    svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
    owner = await make_member(session, id=1)
    other = await make_member(session, id=2)
    personal = await svc.create_task(
        title="Personal", assignee_id=owner.id, visibility=TaskVisibility.PERSONAL
    )
    shared = await svc.create_task(
        title="Shared", assignee_id=owner.id, visibility=TaskVisibility.SHARED
    )
    tasks_for_other = await svc.list_tasks(member_id=other.id)
    assert personal not in tasks_for_other
    assert shared in tasks_for_other
```

### Testing Takeover Limit

Verify limit enforcement:

```python
@pytest.mark.anyio
async def test_takeover_limit_enforced(session, fake_sender):
    svc = TaskService(session, fake_sender, max_takeovers_per_week=3)
    assignee = await make_member(session, id=1)
    taker = await make_member(session, id=2)
    for _ in range(3):
        task = await svc.create_task("Task", assignee_id=assignee.id)
        await svc.claim_completion(task.id, taker.id)
    
    fourth = await svc.create_task("Fourth", assignee_id=assignee.id)
    with pytest.raises(TakeoverLimitExceededError):
        await svc.claim_completion(fourth.id, taker.id)
```

### Testing Dynamic System Prompt

Verify context assembly:

```python
@pytest.mark.anyio
async def test_system_prompt_includes_members(agent_deps):
    await agent_deps.member_service.register_pending("wa_123")
    await agent_deps.member_service.set_name("wa_123", "Alice")
    
    ctx = RunContext(deps=agent_deps, retry=0, messages=[])
    prompt = await _household_ctx(ctx)
    
    assert "Alice" in prompt
    assert "ID 1" in prompt
```

### Testing Retry Wrapper

Mock transient failures to verify retry behavior:

```python
@pytest.mark.anyio
async def test_agent_retry_on_timeout(agent, agent_deps):
    call_count = 0
    original_run = agent.run
    
    async def flaky_run(message, deps):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("LLM timeout")
        return await original_run(message, deps)
    
    with patch.object(agent, "run", flaky_run):
        result = await call_agent_with_retry(agent, "hello", agent_deps)
    
    assert call_count == 3
```

### Testing Scheduler Jobs with NullSender

Use a spy to verify no messages sent when not needed:

```python
@pytest.mark.anyio
async def test_reset_recurring_sends_no_message(session_factory):
    calls = []
    class SpySender:
        async def send(self, chat_id, text):
            calls.append((chat_id, text))
    
    await reset_recurring_tasks(session_factory)
    assert calls == []
```

### Conventions

- **Test naming**: `test_<action>_<scenario>` — e.g., `test_create_task_with_recurrence`, `test_verify_own_task_rejected`. Describes what's being tested and the interesting condition.
- **Arrange-Act-Assert**, one assert concept per test. Multiple `assert` lines are fine if they check facets of the same result.
- **No mocking internals.** Mock at protocol boundaries (`MessageSender`, HTTP calls to WAHA/LLM), never mock service methods or private functions. If a test needs to mock deep internals, the code needs refactoring.
- **Hypothesis for domain invariants.** Property-based testing for state machines and validation logic.
- **Factory helpers over raw constructors.** `make_task()`, `make_member()` helpers in `conftest.py` with sensible defaults:

```python
def make_task(
    title: str = "Test task",
    status: TaskStatus = TaskStatus.PENDING,
    assignee_id: int = 1,
    **overrides,
) -> Task:
    return Task(title=title, status=status, assignee_id=assignee_id, **overrides)

def make_member(
    session: AsyncSession,
    id: int | None = None,
    whatsapp_id: str = "wa_123",
    name: str = "Test Member",
    status: MemberStatus = MemberStatus.ACTIVE,
) -> Member:
    member = Member(id=id, whatsapp_id=whatsapp_id, name=name, status=status)
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member
```

- **Integration tests use `httpx.AsyncClient` with the app.** Test the full HTTP path for webhook and admin routes:

```python
from httpx import ASGITransport, AsyncClient

@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- **Mark async tests** with `pytest.mark.anyio` (or configure `anyio` as the default async backend in `pyproject.toml`).
