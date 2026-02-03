# Dependency Injection

This page describes dependency injection patterns for Pydantic AI agents.

## Context

Never use global state. Use Pydantic AI's `RunContext[Deps]` to inject the
Database Connection, User ID, User Phone, User Name, User Role, and Current Time.

Using dependency injection ensures that agents are testable, thread-safe, and
have clear dependencies. Global state makes code difficult to test and reason
about.

## Base Deps Structure

The `Deps` dataclass is defined in `src/agents/base.py`:

```python
"""Base utilities and dependencies for Pydantic AI agents."""

from dataclasses import dataclass
from datetime import datetime

from pocketbase import PocketBase


@dataclass
class Deps:
    """Dependencies injected into agent RunContext."""

    db: PocketBase
    user_id: str
    user_phone: str
    user_name: str
    user_role: str
    current_time: datetime
```

### Deps Fields

| Field | Type | Description |
|-------|------|-------------|
| `db` | `PocketBase` | Database connection for all data operations |
| `user_id` | `str` | ID of the current user making the request |
| `user_phone` | `str` | Phone number of the current user (E.164 format) |
| `user_name` | `str` | Display name of the current user |
| `user_role` | `str` | Role of the current user (e.g., "admin", "member") |
| `current_time` | `datetime` | Current time for timestamping operations |

## Using RunContext[Deps]

Tools receive dependencies via the `RunContext[Deps]` parameter:

```python
from pydantic_ai import RunContext
from src.agents.base import Deps

async def tool_log_chore(ctx: RunContext[Deps], params: LogChore) -> str:
    """Log a chore completion with user context."""
    # Access dependencies via ctx.deps
    user_id = ctx.deps.user_id
    user_name = ctx.deps.user_name

    # Use database connection
    chore = await ctx.deps.db.get_record("chores", params.chore_id)

    # Use current time for timestamp
    timestamp = ctx.deps.current_time.isoformat()

    return f"Logged chore at {timestamp} by {user_name}"
```

## Building Dependencies

Dependencies are built before running the agent:

```python
from src.agents.base import Deps
from datetime import datetime
from pocketbase import PocketBase

async def build_deps(*, db: PocketBase, user_phone: str) -> Deps | None:
    """Build dependencies for agent execution."""
    # Look up user by phone number
    user = await user_service.get_user_by_phone(phone=user_phone)
    if not user:
        return None

    # Build dependencies
    return Deps(
        db=db,
        user_id=user["id"],
        user_phone=user["phone"],
        user_name=user["name"],
        user_role=user["role"],
        current_time=datetime.now(),
    )
```

## Running the Agent

Pass the built dependencies to the agent:

```python
async def run_agent(*, user_message: str, deps: Deps) -> str:
    """Run the agent with dependencies."""
    agent = get_agent()

    result = await agent.run(
        user_message,
        deps=deps,
        message_history=[],
        instructions="System prompt here",
    )

    return result.output
```

## Negative Case: Global State

Incorrect pattern that should be avoided:

```python
# Bad - using global state
db_client = PocketBase("http://localhost:8090")

async def tool_bad_example(params: SomeParams) -> str:
    """Uses global database connection - not thread-safe or testable."""
    # This uses a global connection - bad practice!
    record = await db_client.get_record("some_collection", params.id)
    return "Done"
```

Correct pattern using dependency injection:

```python
# Good - using dependency injection
async def tool_good_example(ctx: RunContext[Deps], params: SomeParams) -> str:
    """Uses injected database connection - thread-safe and testable."""
    # This uses the injected connection from context
    record = await ctx.deps.db.get_record("some_collection", params.id)
    return "Done"
```
