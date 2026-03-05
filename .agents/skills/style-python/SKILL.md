---
name: style-python
description: Code style conventions for Python in this project
user-invocable: false
---

# Python Code Style

> Style guide: PEP 8 (https://peps.python.org/pep-0008/) + Google Python Style Guide conventions
> Tooling: ruff (linting + formatting), ty (type checking) — configured in pyproject.toml

## Naming Conventions

```python
# Variables and functions: snake_case
task_id = 1
async def create_task(...) -> Task: ...

# Classes: PascalCase
class TaskService: ...
class MessageJob: ...

# Enums: PascalCase class, UPPER_SNAKE members
class TaskStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    VERIFIED = "verified"

# Constants: UPPER_SNAKE in config.py
MAX_RETRIES = 5
DEFAULT_RATE_LIMIT = 10

# Modules: lowercase snake_case, singular for models, plural for tool groups
# models/task.py, models/member.py
# agent/tools/tasks.py, agent/tools/analytics.py

# Private attributes: single leading underscore
class WAHAClient:
    def __init__(self, url: str) -> None:
        self._url = url  # private, not public API
```

## Import & Module Structure

```python
# Ordering: stdlib → third-party → local (ruff enforces this)
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI
from pydantic_ai import Agent
from sqlmodel import Field, SQLModel, select

from choresir.config import Settings
from choresir.errors import NotFoundError
from choresir.models.task import Task
```

Import rules:
- No wildcard imports (`from x import *`), except `from fasthtml.common import *` which is FastHTML convention
- Prefer absolute imports (`from choresir.models.task import Task`) over relative
- Group by: stdlib, third-party, local — separated by blank lines (ruff auto-fixes)

## Type Annotations

All public functions and methods must have full type annotations. Use modern syntax (Python 3.10+):

```python
# Use X | Y instead of Optional[X] / Union[X, Y]
def get_task(task_id: int) -> Task | None: ...

# Use built-in generics (list, dict, tuple) not typing.List etc.
async def list_tasks(session: AsyncSession) -> list[Task]: ...

# Use Annotated for dependency injection metadata
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Dataclasses for simple deps containers
from dataclasses import dataclass

@dataclass
class AgentDeps:
    session: AsyncSession
    sender: MessageSender
```

Strictness: `ty` is configured as the type checker. Fix all type errors before committing.

## Documentation

```python
# Public functions: one-line summary, then params/returns only if non-obvious
async def create_task(
    session: AsyncSession,
    title: str,
    assignee_id: int,
    deadline: datetime | None = None,
) -> Task:
    """Create and persist a new task, returning the saved instance."""
    ...

# Classes: brief description of responsibility
class TaskService:
    """Domain logic for task lifecycle: creation, completion, verification, recurrence."""
    ...

# Private helpers: docstring optional if name is self-explanatory
def _build_status_filter(status: TaskStatus) -> ColumnElement: ...
```

Avoid redundant docstrings that just restate the function name. Document the "why" and non-obvious behavior, not the "what".

## Formatting Rules

Enforced by ruff format (auto-applied):
- **Line length**: 88 characters (black-compatible)
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: double quotes for strings
- **Trailing commas**: ruff adds trailing commas in multi-line function arguments and data structures
- **Blank lines**: 2 between top-level definitions, 1 between methods

Manual conventions (not auto-enforced):
- Use `f-strings` for string interpolation, not `.format()` or `%`
- Use `match` statement for exhaustive enum dispatch (Python 3.10+)
- Place `# noqa` comments with a reason when suppressing linting rules

Run `poe check` before committing — it runs ruff, ty, bandit, vulture, complexipy, and pytest.
