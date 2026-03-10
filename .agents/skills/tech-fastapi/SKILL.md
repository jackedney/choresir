---
name: tech-fastapi
description: Reference guide for FastAPI — HTTP framework, ASGI server for webhook handling
user-invocable: false
---

# FastAPI

> Purpose: HTTP framework, ASGI server — webhook handling, dependency injection, admin sub-app mounting
> Docs: https://fastapi.tiangolo.com
> Version researched: 0.115+

## Quick Start

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: start workers, scheduler
    yield
    # shutdown: cleanup

app = FastAPI(lifespan=lifespan)
```

## Common Patterns

### Webhook endpoint — return 200 immediately, process async

```python
from fastapi import APIRouter, Request, Header, HTTPException
from typing import Annotated

router = APIRouter()

@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
):
    body = await request.json()
    # enqueue job, return immediately
    return {"status": "ok"}
```

### Dependency injection for shared resources

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_session() -> AsyncSession:
    async with session_factory() as session:
        yield session

SessionDep = Annotated[AsyncSession, Depends(get_session)]

@router.get("/items")
async def list_items(session: SessionDep):
    ...
```

### Mount a sub-application (FastHTML admin)

```python
from fasthtml.common import fast_app

admin_app, rt = fast_app()

app.mount("/admin", admin_app)
```

### Exception handlers for domain errors

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from choresir.errors import WebhookAuthError, RateLimitExceededError

@app.exception_handler(WebhookAuthError)
async def webhook_auth_handler(request: Request, exc: WebhookAuthError):
    return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

@app.exception_handler(RateLimitExceededError)
async def rate_limit_handler(request: Request, exc: RateLimitExceededError):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
```

### Background coroutines in lifespan

```python
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(message_worker_loop())
    yield
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)
```

## Gotchas & Pitfalls

- **Lifespan vs startup/shutdown events**: Use `lifespan` context manager (preferred since 0.93). The old `@app.on_event("startup")` is deprecated.
- **`BackgroundTasks` are not durable**: FastAPI's built-in `BackgroundTasks` run in-process and are lost on crash. Use the SQLite job queue for durable processing.
- **Router prefix vs mount**: `app.include_router(router, prefix="/api")` for FastAPI routers; `app.mount("/admin", sub_app)` for full ASGI sub-applications.
- **Request body can only be read once**: Call `await request.json()` or `await request.body()` once; cache the result if needed downstream.
- **`Header()` uses underscores**: FastAPI normalizes HTTP headers — `X-API-Key` becomes `x_api_key` in the function parameter.

## Idiomatic Usage

Prefer `Annotated` dependencies over default parameter values:

```python
# Good
async def endpoint(session: Annotated[AsyncSession, Depends(get_session)]): ...

# Avoid
async def endpoint(session: AsyncSession = Depends(get_session)): ...
```

Return Pydantic models directly — FastAPI serializes them automatically. Avoid building dicts manually for responses.
