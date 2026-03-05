---
name: tech-alembic
description: Reference guide for Alembic — database migrations for SQLModel/SQLite
user-invocable: false
---

# Alembic

> Purpose: Database migrations — schema management for SQLModel/SQLite with async engine
> Docs: https://alembic.sqlalchemy.org
> Version researched: 1.x

## Quick Start

```bash
# Initialize (run once)
alembic init alembic

# Generate migration from model changes
alembic revision --autogenerate -m "add task table"

# Apply migrations
alembic upgrade head
```

## Common Patterns

### env.py for async SQLite with SQLModel

```python
# alembic/env.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_engine_from_config
from sqlalchemy import pool
from alembic import context
from sqlmodel import SQLModel

# Import ALL models so SQLModel.metadata is populated
from choresir.models.task import Task  # noqa: F401
from choresir.models.member import Member  # noqa: F401
from choresir.models.job import MessageJob  # noqa: F401

target_metadata = SQLModel.metadata

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    config = context.config
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### alembic.ini for aiosqlite

```ini
[alembic]
script_location = alembic
sqlalchemy.url = sqlite+aiosqlite:///choresir.db
```

### Programmatic migration on app startup

```python
from alembic import command, config as alembic_config
from sqlalchemy.ext.asyncio import create_async_engine

async def run_migrations(database_url: str) -> None:
    cfg = alembic_config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)

    def _run(connection):
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(_run)
    await engine.dispose()
```

### Creating a manual migration

```python
# alembic/versions/abc123_add_recurrence_column.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column("task", sa.Column("recurrence", sa.String(), nullable=True))

def downgrade():
    op.drop_column("task", "recurrence")
```

## Gotchas & Pitfalls

- **Import all models in env.py**: Alembic can only autogenerate migrations for tables it knows about. If a model isn't imported before `SQLModel.metadata` is referenced, its table is invisible to autogenerate.
- **SQLite ALTER TABLE limitations**: SQLite does not support `ALTER COLUMN` or `DROP COLUMN` in older versions. Alembic's `batch_migrations` mode is required for column changes on SQLite. Enable with `render_as_batch=True` in `context.configure(...)`.
- **`NullPool` is required for async**: When using async engine in migrations, use `poolclass=pool.NullPool` to avoid connection pool lifecycle issues.
- **Autogenerate doesn't detect everything**: Alembic autogenerate misses check constraints, partial indexes, and some server defaults. Review generated migrations before applying.
- **Migration files are version-controlled**: Never edit a migration that has been applied to production. Create a new migration to fix issues.

## Idiomatic Usage

Enable batch mode for SQLite to support column alterations:

```python
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    render_as_batch=True,  # Required for SQLite column changes
)
```

Run migrations at application startup (before accepting requests) in the lifespan handler, not as a separate deployment step — keeps single-container deployments simple.
