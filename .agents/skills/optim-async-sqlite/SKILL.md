---
name: optim-async-sqlite
description: Optimisation patterns for async SQLite access — relevant to choresir's single-DB, single-process architecture
user-invocable: false
---

# Async SQLite Optimisation

> Relevance: Choresir uses a single SQLite database for all components (job queue, task data, member data, scheduler). Performance depends on efficient async access patterns and SQLite configuration.

## Key Principles

1. **SQLite is single-writer**: Only one write transaction can proceed at a time. Keep write transactions short — read what you need, write once, commit immediately.
2. **aiosqlite runs in a thread pool**: Async SQLite (via aiosqlite) offloads I/O to a thread. Multiple coroutines can be "waiting" concurrently, but SQLite serializes writes internally.
3. **Batch reads, minimize round trips**: Fetch all data needed for an operation in one query rather than N+1 queries.

## Recommended Patterns

### Enable WAL mode for read/write concurrency

```python
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine("sqlite+aiosqlite:///choresir.db")

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

WAL mode allows concurrent readers while a writer is active — critical for the job queue + agent running simultaneously.

### Efficient job queue claim (atomic update)

```python
# Claim a pending job atomically — avoid SELECT then UPDATE (race condition)
from sqlalchemy import update, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

async def claim_next_job(session: AsyncSession) -> MessageJob | None:
    # Use a CTE or subquery to claim atomically
    stmt = (
        update(MessageJob)
        .where(
            MessageJob.status == "pending",
            MessageJob.run_after <= datetime.utcnow(),
        )
        .values(status="processing", claimed_at=datetime.utcnow())
        .returning(MessageJob)
    )
    result = await session.exec(stmt)
    await session.commit()
    return result.first()
```

### Avoid N+1 queries with joinedload

```python
from sqlalchemy.orm import selectinload

# Fetch tasks with assignees in one query
stmt = select(Task).options(selectinload(Task.assignee))
tasks = (await session.exec(stmt)).all()
```

### Use `expire_on_commit=False`

```python
# Prevents SQLAlchemy from expiring object attributes after commit
# which would trigger lazy loads (sync) in async context
session_factory = async_sessionmaker(engine, expire_on_commit=False)
```

### Short, focused sessions

```python
# Good: open session, do work, close
async with session_factory() as session:
    task = await session.get(Task, task_id)
    task.status = "claimed"
    await session.commit()

# Avoid: long-lived sessions spanning multiple unrelated operations
```

## Data Structure Choices

| Need | Choice | Why |
|------|---------|-----|
| Job queue | SQLite table with `status` column | Durable across restarts; dedup via PK |
| Rate limit tracking | `aiolimiter` (in-memory) | Sub-millisecond; doesn't need persistence |
| Session cache | Python dict | Fixed small household — no eviction needed |
| Scheduler state | APScheduler in-memory store | Simple; schedules registered at startup |

## Measurement

Profile slow queries with SQLAlchemy echo:

```python
engine = create_async_engine("sqlite+aiosqlite:///choresir.db", echo=True)
```

Use `EXPLAIN QUERY PLAN` for complex queries:

```python
result = await session.exec(text("EXPLAIN QUERY PLAN SELECT ..."))
```

Track message processing latency with structured logging: log `job.claimed_at` vs `job.completed_at`.

## Common Pitfalls

- **Missing indexes**: Add `index=True` to frequently queried columns in SQLModel (`whatsapp_id`, `status`, `run_after`, `assignee_id`). Missing indexes cause full table scans.
- **Writing inside a long read transaction**: Avoid doing heavy reads and then writing in the same transaction — SQLite blocks other writers for the full transaction duration.
- **`aiosqlite` thread pool saturation**: Under very high load, the aiosqlite thread pool can become a bottleneck. For a household app (tiny load), this is irrelevant.
- **Forgetting `await session.commit()`**: SQLAlchemy async sessions do not auto-commit. Changes are silently dropped if the session closes without a commit.
