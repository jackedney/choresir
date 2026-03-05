---
name: tech-sqlmodel
description: Reference guide for SQLModel — ORM combining Pydantic and SQLAlchemy for SQLite async access
user-invocable: false
---

# SQLModel

> Purpose: ORM (Pydantic + SQLAlchemy) — data models, async SQLite access, session management
> Docs: https://sqlmodel.tiangolo.com
> Version researched: 0.0.24+

## Quick Start

```python
from sqlmodel import SQLModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    status: str = "pending"

engine = create_async_engine("sqlite+aiosqlite:///choresir.db")
session_factory = async_sessionmaker(engine, expire_on_commit=False)
```

## Common Patterns

### Define a table model

```python
from sqlmodel import SQLModel, Field
from typing import Optional

class Member(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(unique=True, index=True)
    name: str | None = None
    role: str = "member"  # use enums in practice
    status: str = "pending"
```

### Async CRUD operations

```python
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

async def get_task(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)

async def list_tasks(session: AsyncSession) -> list[Task]:
    result = await session.exec(select(Task))
    return result.all()

async def create_task(session: AsyncSession, task: Task) -> Task:
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task

async def update_task(session: AsyncSession, task: Task, **updates) -> Task:
    task.sqlmodel_update(updates)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task
```

### Session factory as async context manager

```python
async def get_session():
    async with session_factory() as session:
        yield session
```

### Relationships

```python
class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    assignee_id: int = Field(foreign_key="member.id")
    assignee: "Member | None" = Relationship(back_populates="tasks")

class Member(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tasks: list[Task] = Relationship(back_populates="assignee")
```

### INSERT OR IGNORE for deduplication

```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

stmt = sqlite_insert(MessageJob).values(id=message_id, status="pending")
stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
await session.exec(stmt)
await session.commit()
```

## Gotchas & Pitfalls

- **`table=True` vs Pydantic-only**: Omit `table=True` for validation-only models (e.g., request bodies, response shapes). Only `table=True` models create DB tables.
- **`expire_on_commit=False`**: Essential for async usage — prevents SQLAlchemy from expiring attributes after commit (which would trigger sync lazy-load).
- **Lazy loading is sync**: Never access relationship attributes after session close. Use explicit `selectinload` or `joinedload` options, or re-query.
- **`session.exec()` vs `session.execute()`**: Use `session.exec()` for SQLModel `select()` statements (returns typed results); use `session.execute()` for raw SQLAlchemy constructs.
- **`sqlmodel_update()`**: Preferred over manually setting attributes for partial updates — respects exclude_unset semantics.
- **Alembic autogenerate with SQLModel**: Import all models in `env.py` before referencing `SQLModel.metadata` so Alembic sees all tables.

## Idiomatic Usage

Separate table models (in `models/`) from service logic (in `services/`). Models are pure data — no methods that hit the DB. Services receive `AsyncSession` and own all query logic.

```python
# models/task.py — pure data
class Task(SQLModel, table=True): ...

# services/task_service.py — all DB logic
class TaskService:
    def __init__(self, session: AsyncSession): ...
    async def create_task(self, ...) -> Task: ...
```
