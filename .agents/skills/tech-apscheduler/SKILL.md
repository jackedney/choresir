---
name: tech-apscheduler
description: Reference guide for APScheduler v4 — async cron scheduler for reminders, summaries, and recurring task resets
user-invocable: false
---

# APScheduler v4

> Purpose: Task scheduling — cron-triggered async jobs for reminders, daily summary, weekly leaderboard, recurring task resets
> Docs: https://apscheduler.readthedocs.io / https://github.com/agronholm/apscheduler
> Version researched: 4.x (pre-release — verify stability before use in production)

## Quick Start

```python
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger

async with AsyncScheduler() as scheduler:
    await scheduler.add_schedule(my_job, CronTrigger(hour=9, minute=0), id="daily")
    await scheduler.run_until_stopped()
```

## Common Patterns

### FastAPI lifespan integration

```python
from contextlib import asynccontextmanager
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

scheduler: AsyncScheduler | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    async with AsyncScheduler() as sched:
        scheduler = sched
        await _register_jobs(sched)
        await sched.start_in_background()
        yield

async def _register_jobs(sched: AsyncScheduler) -> None:
    await sched.add_schedule(send_daily_summary, CronTrigger(hour=20), id="daily_summary")
    await sched.add_schedule(send_weekly_leaderboard, CronTrigger(day_of_week="sun", hour=18), id="weekly_leaderboard")
    await sched.add_schedule(send_overdue_reminders, CronTrigger(hour="8,12,18"), id="overdue_reminders")
    await sched.add_schedule(reset_recurring_tasks, CronTrigger(minute=0), id="recurring_reset")

app = FastAPI(lifespan=lifespan)
```

### CronTrigger patterns

```python
from apscheduler.triggers.cron import CronTrigger

# Every day at 8pm
CronTrigger(hour=20, minute=0)

# Every Sunday at 6pm
CronTrigger(day_of_week="sun", hour=18, minute=0)

# Every hour (for overdue reminders)
CronTrigger(minute=0)

# From crontab string: "0 20 * * *"
CronTrigger.from_crontab("0 20 * * *")
```

### Job function with DB access

```python
async def send_daily_summary() -> None:
    async with session_factory() as session:
        stats = await analytics_service.daily_stats(session)
        message = format_daily_summary(stats)
        await waha_client.send(GROUP_CHAT_ID, message)
```

### Conflict policy on schedule registration

```python
from apscheduler import ConflictPolicy

await sched.add_schedule(
    my_job,
    CronTrigger(hour=9),
    id="daily_job",
    conflict_policy=ConflictPolicy.replace,  # update if already exists
)
```

## Gotchas & Pitfalls

- **v4 is a pre-release**: API differs significantly from v3. Do not mix v3 and v4 documentation. Key difference: `AsyncScheduler` replaces `BackgroundScheduler` + executor model.
- **`start_in_background()` vs `run_until_stopped()`**: Use `start_in_background()` for web apps (returns control to FastAPI); `run_until_stopped()` for standalone scheduler processes.
- **Sunday is weekday 0**: CronTrigger follows crontab convention (0 = Sunday), unlike Python's `datetime.weekday()` (0 = Monday).
- **Job functions must be importable**: APScheduler serializes job references. Functions defined inside `if __name__ == "__main__"` blocks won't work.
- **In-memory data store**: Default data store is in-memory; schedules are lost on restart. For persistence, use SQLAlchemyDataStore.
- **`IntervalTrigger` fires immediately**: Unlike v3, v4's `IntervalTrigger` starts on first tick without delay.

## Idiomatic Usage

Keep job functions thin — they should fetch data and delegate to services:

```python
# Good
async def send_overdue_reminders() -> None:
    async with session_factory() as session:
        overdue = await task_service.get_overdue(session)
        for task in overdue:
            await messaging.send(task.assignee.chat_id, f"Reminder: {task.title}")

# Avoid putting business logic in job functions
```

Register all schedules in one place (`scheduler/setup.py`) so job configuration is easy to audit.
