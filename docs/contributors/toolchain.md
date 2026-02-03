# Toolchain & Style

This page describes the toolchain and coding style standards used in WhatsApp Home Boss.

## The Astral Stack

We strictly enforce the **Astral** toolchain standards for code quality and developer experience.

### Core Tools

#### Package Manager: `uv`

Use `uv` for all dependency management.

**Why `uv`?**

- Written in Rust (extremely fast)
- Drop-in replacement for `pip`
- Better dependency resolution
- Virtual environment management built-in
- Lock file support for reproducible builds

**Usage:**

```bash
# Install dependencies from pyproject.toml
uv sync

# Add a new dependency
uv add fastapi

# Run a command in the virtual environment
uv run pytest
```

#### Linter/Formatter: `ruff`

Use `ruff` as the replacement for Black, Isort, and Flake8.

**Why `ruff`?**

- Written in Rust (100-200x faster than alternatives)
- Combined functionality: formatting + linting + import sorting
- Compatible with Black formatting
- No Python dependency (runs as standalone binary)

#### Type Checker: `ty`

Use `ty` (Astral's high-performance type checker).

**Why `ty`?**

- Written in Rust (10-60x faster than mypy/pyright)
- Better error messages
- First-class support for modern Python features
- Integrates well with existing tooling

## Formatting Rules

All code must follow these formatting standards:

### Line Length

### 120 characters maximum

```python
# Keep lines under 120 characters
async def create_chore(*, title: str, recurrence: str, assigned_to: str | None = None) -> dict[str, Any]:
    """Create a new chore."""
    # ...
```

### Quotes

**Double quotes (`"`) preferred**

```python
# Use double quotes for strings
message = "Hello, world!"

# Use double quotes for docstrings
"""This is a docstring."""

# Use double quotes for f-strings
greeting = f"Hello, {name}!"
```

### Trailing Commas

### Mandatory for multi-line lists/dictionaries

```python
# Good: trailing commas
chores = [
    "wash dishes",
    "vacuum living room",
    "clean bathroom",
]

users = {
    "id": "user123",
    "name": "Alice",
    "phone": "+1234567890",
}

# Bad: no trailing commas (ruff will fix this)
chores = [
    "wash dishes",
    "vacuum living room",
    "clean bathroom"
]
```

### Imports

### Grouped by type: Standard Lib, Third Party, Local

```python
# 1. Standard Library
import logging
from datetime import datetime
from typing import Any

# 2. Third Party
from fastapi import FastAPI
from pydantic import BaseModel
from pocketbase import PocketBase

# 3. Local
from src.domain.models import Chore
from src.services.database import DatabaseService
```

## Coding Conventions

### Functional Preference

**Use standalone functions in modules (`src/services/`) rather than Service Classes,
unless state management requires a class.**

**Rationale:**

- Simpler to test (pure functions are easy to mock)
- Easier to reason about (explicit inputs/outputs)
- No hidden state or side effects
- Fits Python's functional programming style
- No need for dependency injection frameworks

**When to use classes:**

- Stateful components (e.g., `PocketBaseConnectionPool`)
- Scheduler or queue managers that maintain internal state
- When explicit interface contracts are needed (rare)

See [Engineering Patterns](../architecture/patterns.md#functional-preference) for details.

### Keyword-Only Arguments

**Enforce `*` for functions with > 2 parameters.**

**Rationale:**

- Forces explicit argument passing (no positional arguments)
- Improves code readability and reduces bugs
- Makes function signatures self-documenting

**Example:**

```python
# Good: keyword-only arguments
def create_task(*, name: str, due: datetime, user: str, priority: int = 1) -> dict[str, Any]:
    """Create a new task."""
    return {"name": name, "due": due, "user": user, "priority": priority}

# Usage (named arguments required)
create_task(name="Dishes", due=datetime.now(), user="alice")

# Bad: allows positional arguments (avoid)
def create_task(name: str, due: datetime, user: str, priority: int = 1) -> dict[str, Any]:
    # ...
```

### DTOs Only

**Strictly use Pydantic models for passing data between layers. No raw dicts.**

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

### No Custom Exceptions

**Use standard Python exceptions or `FastAPI.HTTPException`.**

**Rationale:**

- Simplicity (no need to define custom exception hierarchy)
- FastAPI's built-in exception handling works automatically
- Standard exceptions are well-understood

**Examples:**

- `ValueError`: Invalid input or configuration
- `KeyError`: Record not found in database
- `ConnectionError`: External service unreachable
- `FastAPI.HTTPException`: HTTP-specific errors with status codes

### No TODOs

**Do not commit `TODO` comments.**

**Rationale:**

- TODOs accumulate and are rarely addressed
- They signal incomplete work
- Use ADRs (Architectural Decision Records) for documented design discussions

**Alternatives:**

- Create a GitHub issue for future work
- Write an ADR for design decisions
- Comment "Note: X needs improvement" with rationale if needed for context

### Minimalist Documentation

**Single-line function descriptions. No verbose Google-style docstrings.**

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

### Strict Typing

**Type hints required for ALL arguments and return values (including `-> None`).**

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

## Running Quality Tools

See [Code Quality](code-quality.md) for detailed instructions on running these tools.

### Quick Reference

```bash
# Format code
uv run ruff format .

# Lint and auto-fix
uv run ruff check . --fix

# Type check
uv run ty check src

# Run tests
uv run pytest
```
