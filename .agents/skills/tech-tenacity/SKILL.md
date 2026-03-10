---
name: tech-tenacity
description: Reference guide for tenacity — retry/backoff decorator for AI model unavailability
user-invocable: false
---

# tenacity

> Purpose: Retry/backoff decorator — handles AI model unavailability with exponential backoff
> Docs: https://tenacity.readthedocs.io
> Version researched: latest

## Quick Start

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def call_llm(message: str) -> str:
    return await agent.run(message)
```

## Common Patterns

### Retry only on specific exceptions

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type((TimeoutError, httpx.RequestError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    reraise=True,
)
async def call_ai_agent(message: str) -> str:
    result = await agent.run(message)
    return result.output
```

### Exponential backoff with jitter (avoids thundering herd)

```python
from tenacity import wait_exponential, wait_random_exponential

# Pure exponential: 2s, 4s, 8s, 16s, ... capped at 60s
wait=wait_exponential(multiplier=1, min=2, max=60)

# Randomized (preferred for distributed systems):
wait=wait_random_exponential(multiplier=1, max=60)
```

### Logging retries

```python
import logging
from tenacity import before_sleep_log, after_log

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=2, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    after=after_log(logger, logging.INFO),
    reraise=True,
)
async def call_ai_agent(message: str) -> str: ...
```

### Using as a context manager (for conditional retry)

```python
from tenacity import Retrying, stop_after_attempt, wait_fixed

async def process_message(message: str) -> str:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_fixed(5),
        reraise=True,
    ):
        with attempt:
            return await agent.run(message)
```

### Worker-level retry (preferred for choresir)

In choresir, retry is managed at the worker level via the SQLite job queue's `run_after` column, not at the function level. Use tenacity only for transient network errors within a single attempt:

```python
# Thin tenacity wrapper for single-call resilience
@retry(
    retry=retry_if_exception_type(httpx.RequestError),
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=10),
    reraise=True,
)
async def _send_to_llm(prompt: str) -> str:
    return await litellm_call(prompt)
```

## Gotchas & Pitfalls

- **`reraise=True` is essential**: Without it, tenacity raises `RetryError` (wrapping the original) after exhausting attempts. Set `reraise=True` to propagate the original exception.
- **Async requires `AsyncRetrying` or `@retry` on `async def`**: The `@retry` decorator automatically handles async functions — no need for `AsyncRetrying` unless using the context manager form.
- **Don't retry on permanent errors**: Only retry on transient failures (timeouts, connection errors, 5xx). Do not retry on validation errors, auth failures, or 4xx responses.
- **Double-retry risk**: If both tenacity and the worker queue retry, a single message can be attempted many more times than intended. Coordinate retry budgets.
- **`stop_after_delay` vs `stop_after_attempt`**: Prefer `stop_after_attempt` for predictable behavior; `stop_after_delay` can leave partial states if the delay window is too short.

## Idiomatic Usage

Apply tenacity at the narrowest scope — wrap only the external call, not the entire business logic function. This makes retry behavior explicit and testable:

```python
# Good — narrow scope
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30), reraise=True)
async def _call_llm(prompt: str) -> str: ...

async def process_message(msg: str) -> str:
    response = await _call_llm(msg)  # retry here
    await save_result(response)       # not retried
    return response
```
