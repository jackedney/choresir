# Engineering Patterns

This page describes the engineering patterns used in WhatsApp Home Boss.

## Functional Preference

**Rule:** Use standalone functions in modules (`src/services/`) rather than Service
Classes, unless state management requires a class.

**Rationale:**

- Simpler to test (pure functions are easy to mock)
- Easier to reason about (explicit inputs/outputs)
- No hidden state or side effects
- Fits Python's functional programming style
- No need for dependency injection frameworks

**Example (Good):**

```python
# src/services/chore_service.py

async def create_chore(
    *,
    title: str,
    recurrence: str,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Create a new chore."""
    schedule_cron = parse_recurrence_to_cron(recurrence)
    deadline = _calculate_next_deadline(schedule_cron)
    chore_data = {
        "title": title,
        "schedule_cron": schedule_cron,
        "assigned_to": assigned_to or "",
        "current_state": ChoreState.TODO,
        "deadline": deadline.isoformat(),
    }
    return await db_client.create_record(collection="chores", data=chore_data)
```

**Example (Avoid):**

```python
# AVOID: Service classes with methods

class ChoreService:
    def __init__(self, db: PocketBase):
        self.db = db

    async def create_chore(self, title: str, recurrence: str) -> dict[str, Any]:
        # ...
```

**When to use classes:**

- Stateful components (e.g., `PocketBaseConnectionPool` in `db_client.py`)
- Scheduler or queue managers that maintain internal state
- When explicit interface contracts are needed (rare)

## Keyword-Only Arguments

**Rule:** Enforce `*` for functions with > 2 parameters.

**Rationale:**

- Forces explicit argument passing (no positional arguments)
- Improves code readability and reduces bugs
- Makes function signatures self-documenting

**Example:**

```python
def create_task(*, name: str, due: datetime, user: str, priority: int = 1) -> dict[str, Any]:
    """Create a new task."""
    # All arguments must be named when calling this function
    return {"name": name, "due": due, "user": user, "priority": priority}

# Usage (named arguments required)
create_task(name="Dishes", due=datetime.now(), user="alice")
```

## DTOs Only

**Rule:** Strictly use Pydantic models for passing data between layers. No raw dicts.

**Rationale:**

- Type safety and validation
- Clear contracts between layers
- Automatic JSON serialization
- IDE autocomplete and type checking

**Example:**

```python
# src/domain/chore.py

from pydantic import BaseModel, Field

class Chore(BaseModel):
    """Chore data transfer object."""
    id: str = Field(..., description="Unique chore ID from PocketBase")
    title: str = Field(..., description="Chore title")
    current_state: ChoreState = Field(default=ChoreState.TODO)
    deadline: datetime = Field(..., description="Next deadline")

# Usage in service
async def create_chore(*, chore: Chore) -> dict[str, Any]:
    """Create a chore from validated DTO."""
    return await db_client.create_record(collection="chores", data=chore.model_dump())
```

**Negative Case:**

```python
# AVOID: Passing raw dicts

async def create_chore(*, chore_data: dict[str, Any]) -> dict[str, Any]:
    # What fields are expected? No validation, no type safety
    return await db_client.create_record(collection="chores", data=chore_data)
```

## No Custom Exceptions

**Rule:** Use standard Python exceptions or `FastAPI.HTTPException`.

**Rationale:**

- Simplicity (no need to define custom exception hierarchy)
- FastAPI's built-in exception handling works automatically
- Standard exceptions are well-understood

**Examples:**

- `ValueError`: Invalid input or configuration
- `KeyError`: Record not found in database
- `ConnectionError`: External service unreachable
- `FastAPI.HTTPException`: HTTP-specific errors with status codes

**Example:**

```python
# src/services/chore_service.py

async def mark_pending_verification(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to PENDING_VERIFICATION state."""
    chore = await db_client.get_record(collection="chores", record_id=chore_id)

    if chore["current_state"] != ChoreState.TODO:
        raise ValueError(
            f"Cannot transition from {chore['current_state']} to PENDING_VERIFICATION"
        )

    return await chore_state_machine.transition_to_pending_verification(chore_id=chore_id)
```

## No TODOs

**Rule:** Do not commit `TODO` comments.

**Rationale:**

- TODOs accumulate and are rarely addressed
- They signal incomplete work
- Use ADRs (Architectural Decision Records) for documented design discussions

**Alternatives:**

- Create a GitHub issue for future work
- Write an ADR for design decisions
- Comment "Note: X needs improvement" with rationale if needed for context

## Minimalist Documentation

**Rule:** Single-line function descriptions. No verbose Google-style docstrings.

**Rationale:**

- Code should be self-documenting
- Docstrings add noise and are rarely kept in sync
- Type hints describe signatures
- Function names describe purpose

**Example (Good):**

```python
async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    """Create a new chore."""
    schedule_cron = parse_recurrence_to_cron(recurrence)
    # ...
```

**Example (Avoid):**

```python
# AVOID: Verbose Google-style docstrings

async def create_chore(
    *,
    title: str,
    recurrence: str,
) -> dict[str, Any]:
    """Create a new chore in the database.

    This function validates the recurrence string, converts it to CRON format,
    calculates the initial deadline, creates a new chore record in PocketBase,
    and returns the created record.

    Args:
        title: The title of the chore to create (e.g., "Wash Dishes")
        recurrence: The recurrence string in natural language or CRON format

    Returns:
        A dictionary containing the created chore record with fields:
        - id: The unique ID of the chore
        - title: The chore title
        - schedule_cron: The CRON expression for scheduling
        - assigned_to: The assigned user ID
        - current_state: The initial state (always TODO)
        - deadline: The first deadline datetime

    Raises:
        ValueError: If the recurrence string cannot be parsed
        db_client.DatabaseError: If the database operation fails

    Example:
        >>> chore = await create_chore(title="Dishes", recurrence="daily")
        >>> print(chore["id"])
        "abc123"
    """
    # ...
```

## Strict Typing

**Rule:** Type hints required for ALL arguments and return values (including `-> None`).

**Rationale:**

- Type checking with `ty` catches bugs early
- IDE autocomplete and refactoring support
- Self-documenting code
- Enables static analysis

**Example:**

```python
# All arguments and return values typed

async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    """Create a new chore."""
    pass

def log_chore_completion(*, user_id: str, chore_id: str) -> None:
    """Log chore completion to audit trail."""
    pass

def get_chore_state(chore: dict[str, Any]) -> ChoreState:
    """Extract and validate chore state."""
    return ChoreState(chore["current_state"])
```

**Missing types:**

```python
# AVOID: Missing type hints

async def create_chore(title, recurrence):  # Missing types
    pass

def log_chore_completion(user_id, chore_id):  # Missing -> None
    pass
```

## Dependency Injection with RunContext

**Rule:** Never use global state. Use Pydantic AI's `RunContext[Deps]` to inject dependencies.

**Rationale:**

- Explicit dependencies (no hidden globals)
- Easier testing (can inject mock dependencies)
- Type-safe access to dependencies
- Consistent with functional philosophy

**Example:**

```python
# src/agents/base.py

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

# Tool using injected dependencies
async def tool_log_chore(ctx: RunContext[Deps], params: LogChoreParams) -> str:
    """Log a chore completion."""
    deps = ctx.deps
    # Access deps.db, deps.user_id, deps.current_time, etc.
```

## Sanitize Database Parameters

**Rule:** Always use `sanitize_param()` for user input in PocketBase filter queries.

**Rationale:**

- Prevents filter injection attacks
- Properly escapes quotes and special characters
- Uses `json.dumps()` for safe escaping

**Example:**

```python
# src/services/chore_service.py

from src.core.db_client import sanitize_param

async def get_chores(*, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get chores with optional filters."""
    filters = []
    if user_id:
        # ALWAYS sanitize user input
        filters.append(f'assigned_to = "{sanitize_param(user_id)}"')

    filter_query = " && ".join(filters) if filters else ""
    return await db_client.list_records(
        collection="chores",
        filter_query=filter_query,
    )
```

**Negative Case (Vulnerable):**

```python
# AVOID: Direct string interpolation (vulnerable to injection)

filters.append(f'assigned_to = "{user_id}"')  # VULNERABLE
```
