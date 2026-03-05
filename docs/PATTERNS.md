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
├── enums.py                # All enums: TaskStatus, VerificationMode, MemberRole, JobStatus, etc.
├── errors.py               # Exception hierarchy
├── webhook/                # Inbound webhook handling
│   ├── __init__.py
│   ├── router.py           # FastAPI router, signature validation
│   └── auth.py             # Webhook authenticity checks
├── worker/                 # Message processing pipeline
│   ├── __init__.py
│   ├── queue.py            # Job queue operations (claim, complete, retry, fail)
│   └── processor.py        # Worker loop, rate limiting, retry logic
├── agent/                  # PydanticAI agent layer
│   ├── __init__.py
│   ├── agent.py            # Agent definition, system prompt assembly
│   ├── registry.py         # Tool registry
│   ├── tools/              # Tool functions grouped by domain
│   │   ├── __init__.py
│   │   ├── tasks.py        # create_task, complete_task, reassign_task, delete_task
│   │   ├── verification.py # verify_completion, reject_completion
│   │   └── analytics.py    # stats, leaderboard queries
│   └── prompts/            # System prompt templates (plain text files)
│       └── base.txt
├── scheduler/              # APScheduler jobs
│   ├── __init__.py
│   ├── setup.py            # Scheduler configuration, job registration
│   └── jobs.py             # Individual job functions (reminders, summaries, resets)
├── admin/                  # FastHTML admin interface
│   ├── __init__.py
│   ├── app.py              # FastHTML app, auth, CSRF
│   └── pages.py            # Page handlers
├── services/               # Shared domain logic (composed, not inherited)
│   ├── __init__.py
│   ├── task_service.py     # Task CRUD, verification, recurrence logic
│   ├── member_service.py   # Member registration, onboarding
│   └── messaging.py        # WAHA API client (send messages)
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
    def __init__(self, base_url: str, api_key: str, http: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._http = http

    async def send(self, chat_id: str, text: str) -> None:
        await self._http.post(f"{self._base_url}/api/sendText", ...)
```

Services accept `MessageSender`, never `WAHAClient` directly. Tests pass a `FakeSender` that records calls.

### Registry Pattern for Agent Tools

Tools self-register via a registry, keeping the agent definition clean and tool groups decoupled:

```python
# agent/registry.py
from dataclasses import dataclass, field
from collections.abc import Callable

@dataclass
class ToolRegistry:
    _tools: list[Callable] = field(default_factory=list)

    def register(self, fn: Callable) -> Callable:
        self._tools.append(fn)
        return fn

    def apply(self, agent: Agent) -> None:
        for tool_fn in self._tools:
            agent.tool(tool_fn)

registry = ToolRegistry()

# agent/tools/tasks.py
from choresir.agent.registry import registry

@registry.register
async def create_task(ctx, title: str, ...) -> str:
    ...

# agent/agent.py
from choresir.agent.registry import registry
registry.apply(agent)
```

Adding a new tool = writing a decorated function in the right file. No imports to update in the agent module.

### Composition-Based Services

Services compose dependencies via `__init__`, never inherit from a base service:

```python
class TaskService:
    def __init__(self, session: AsyncSession, sender: MessageSender) -> None:
        self._session = session
        self._sender = sender

    async def create_task(self, ...) -> Task:
        ...
```

### Enum-Driven State Machines

Task lifecycle and job processing use enums, never raw strings. State transitions are validated:

```python
class TaskStatus(str, Enum):
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

This applies equally to `JobStatus`, `MemberStatus`, and `VerificationMode`.

### Dependency Assembly via App Factory

The FastAPI app factory wires everything together — no global mutable state:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_async_engine(settings.database_url)
    http_client = httpx.AsyncClient()
    sender = WAHAClient(settings.waha_url, settings.waha_api_key, http_client)
    task_service = TaskService(session_factory, sender)
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
    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
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

class RateLimitExceededError(ChoresirError):
    """Per-user or global rate limit hit."""

class WebhookAuthError(ChoresirError):
    """Invalid webhook signature."""
```

### Error Flow by Layer

| Layer | Raises | Catches |
|-------|--------|---------|
| **Services** | Domain errors (`InvalidTransitionError`, `NotFoundError`, `AuthorizationError`) | Nothing — let errors propagate |
| **Agent tools** | Nothing new | Catches domain errors, returns user-friendly strings to the LLM |
| **Webhook router** | `WebhookAuthError` | Nothing — handled by exception handler |
| **Worker/processor** | Nothing new | Catches all errors for retry/fail decisions |
| **FastAPI exception handlers** | — | Maps `WebhookAuthError` to 401, `RateLimitExceededError` to 429 |

### Principles

- **Services raise, boundaries catch.** Domain logic never silences errors. Translation to HTTP responses or LLM-friendly messages happens at the edges.
- **Agent tools return strings, never raise.** A tool that raises kills the agent run. Catch domain errors and return descriptive text so the LLM can communicate the problem naturally:

```python
@registry.register
async def complete_task(ctx, task_id: int, member_id: int) -> str:
    try:
        await task_service.claim_completion(task_id, member_id)
        return "Task marked as complete, awaiting verification."
    except NotFoundError:
        return "That task doesn't exist."
    except AuthorizationError as e:
        return str(e)
```

- **Structured logging at catch sites.** Log with structured context (task ID, member ID, error type), not string-interpolated tracebacks.
- **Retry decisions in the worker only.** The worker catches exceptions from the agent layer and decides: transient failure (LLM timeout) leads to retry with backoff via `run_after`; permanent failure (max attempts) leads to marking `failed` and logging.
- **No bare `except`.** Always catch specific types. The only broad catch is `except Exception` in the worker loop (to prevent a single message from crashing the process), and it logs the full traceback before marking the job failed.

## Testing Patterns

### Structure

```
tests/
├── conftest.py             # Shared fixtures: async engine, session, fake sender, app client
├── unit/                   # Pure logic, no I/O
│   ├── test_transitions.py # State machine validation
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
```

### Conventions

- **Test naming**: `test_<action>_<scenario>` — e.g., `test_create_task_with_recurrence`, `test_verify_own_task_rejected`. Describes what's being tested and the interesting condition.
- **Arrange-Act-Assert**, one assert concept per test. Multiple `assert` lines are fine if they check facets of the same result.
- **No mocking internals.** Mock at protocol boundaries (`MessageSender`, HTTP calls to WAHA/LLM), never mock service methods or private functions. If a test needs to mock deep internals, the code needs refactoring.
- **Hypothesis for domain invariants.** Property-based testing for state machines and validation logic:

```python
from hypothesis import given, strategies as st

@given(st.sampled_from(TaskStatus), st.sampled_from(TaskStatus))
def test_invalid_transitions_raise(current, target):
    if target not in _VALID_TRANSITIONS.get(current, frozenset()):
        task = make_task(status=current)
        with pytest.raises(InvalidTransitionError):
            transition_task(task, target)
```

- **Factory helpers over raw constructors.** `make_task()`, `make_member()` helpers in `conftest.py` with sensible defaults:

```python
def make_task(
    title: str = "Test task",
    status: TaskStatus = TaskStatus.PENDING,
    assignee_id: int = 1,
    **overrides,
) -> Task:
    return Task(title=title, status=status, assignee_id=assignee_id, **overrides)
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
