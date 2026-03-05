---
name: tech-aiolimiter
description: Reference guide for aiolimiter — async rate limiting for global and per-user message processing
user-invocable: false
---

# aiolimiter

> Purpose: Global and per-user async rate limiting — prevents message processing abuse
> Docs: https://github.com/mjpieters/aiolimiter
> Version researched: latest

## Quick Start

```python
from aiolimiter import AsyncLimiter

# Global: max 10 requests per second
global_limiter = AsyncLimiter(10, 1)

async def process():
    async with global_limiter:
        await do_work()
```

## Common Patterns

### Global + per-user limiters

```python
from aiolimiter import AsyncLimiter
from collections import defaultdict

# Global limit: 20 messages per 60 seconds across all users
global_limiter = AsyncLimiter(20, 60)

# Per-user limit: 5 messages per 60 seconds per user
_user_limiters: dict[str, AsyncLimiter] = {}

def get_user_limiter(user_id: str) -> AsyncLimiter:
    if user_id not in _user_limiters:
        _user_limiters[user_id] = AsyncLimiter(5, 60)
    return _user_limiters[user_id]
```

### Applying limits in the worker

```python
from aiolimiter import AsyncLimiter
from choresir.errors import RateLimitExceededError

async def process_job(job: MessageJob, user_id: str) -> None:
    # Check global limit first, then per-user
    if not global_limiter.has_capacity(1):
        raise RateLimitExceededError("Global rate limit reached")

    async with global_limiter:
        user_limiter = get_user_limiter(user_id)
        async with user_limiter:
            await run_agent_for_job(job)
```

### Non-blocking rate limit check

```python
# has_capacity() checks without acquiring — useful for early rejection
if not limiter.has_capacity(1):
    logger.warning("Rate limit exceeded", user_id=user_id)
    raise RateLimitExceededError()

# Blocking acquire (waits until capacity is available)
async with limiter:
    await do_work()
```

### Configuring limits via settings

```python
from choresir.config import Settings

settings = Settings()
global_limiter = AsyncLimiter(
    settings.global_rate_limit_count,
    settings.global_rate_limit_seconds,
)
```

## Gotchas & Pitfalls

- **`AsyncLimiter` is not thread-safe**: It is async-safe (concurrent coroutines) but not thread-safe. Since choresir is single-process async, this is fine.
- **`async with limiter` blocks until capacity available**: This causes the coroutine to wait, not raise. If you want to fail fast on rate limit, use `has_capacity()` first and raise explicitly.
- **Per-user dict grows unbounded**: `_user_limiters` will accumulate entries for every user who has ever sent a message. In a household context (small, fixed user set), this is acceptable. For larger scale, use an LRU cache.
- **Leaky bucket semantics**: `AsyncLimiter(max_rate, time_period)` allows `max_rate` operations per `time_period` seconds. It is a leaky bucket, not a sliding window — bursts up to `max_rate` are allowed.
- **`has_capacity()` is advisory**: The check and acquire are not atomic. For strict limiting, always `async with limiter` and catch the resulting delay.

## Idiomatic Usage

Initialize limiters once at application startup and share them across workers:

```python
# worker/processor.py
from aiolimiter import AsyncLimiter

_global_limiter: AsyncLimiter | None = None
_user_limiters: dict[str, AsyncLimiter] = {}

def init_limiters(settings: Settings) -> None:
    global _global_limiter
    _global_limiter = AsyncLimiter(settings.global_rate_limit, 60)
```

Keep rate limiting in the worker layer, not in services — it's an infrastructure concern, not a domain concern.
