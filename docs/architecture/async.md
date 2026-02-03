# Async & Concurrency

This page describes async and concurrency patterns in WhatsApp Home Boss.

## Async First

**Rule:** Use `async def` for all routes and services.

**Rationale:**

- FastAPI is async-first framework
- Allows concurrent request handling
- Non-blocking I/O for external services (PocketBase, WhatsApp, OpenRouter API)
- Better performance under load

**Example:**

```python
# src/interface/webhook.py

@router.post("")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Receive and validate WAHA webhook POST requests."""
    # All database calls are async
    user = await db_client.get_first_record(
        collection="users",
        filter_query=f'phone = "{sanitize_param(phone)}"',
    )

    # All external API calls are async
    response = await whatsapp_sender.send_text_message(
        to_phone=phone,
        text=message,
    )

    return {"status": "received"}
```

**All service functions use async:**

```python
# src/services/chore_service.py

async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    """Create a new chore."""
    return await db_client.create_record(collection="chores", data={...})

async def get_chores(*, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get chores with optional filters."""
    return await db_client.list_records(collection="chores", filter_query=...)
```

## Background Tasks

**Rule:** WhatsApp Webhooks MUST return `200 OK` immediately. Use `FastAPI.BackgroundTasks` for AI processing.

**Rationale:**

- WhatsApp webhooks timeout after ~30 seconds
- AI processing can take 5-30+ seconds (LLM API latency)
- Immediate response prevents webhook failures and retries
- Background tasks allow async processing

**Implementation:**

```python
# src/interface/webhook.py

@router.post("")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,  # FastAPI BackgroundTasks
) -> dict[str, str]:
    """Receive and validate WAHA webhook POST requests."""
    # 1. Parse and validate immediately (synchronous)
    payload = await request.json()
    message = whatsapp_parser.parse_waha_webhook(payload)

    # 2. Security checks (fast, non-blocking)
    security_result = await webhook_security.verify_webhook_security(
        message_id=message.message_id,
        timestamp_str=message.timestamp,
        phone_number=message.from_phone,
    )

    if not security_result.is_valid:
        raise HTTPException(
            status_code=security_result.http_status_code or 400,
            detail=security_result.error_message,
        )

    # 3. Dispatch to background task (non-blocking)
    background_tasks.add_task(process_webhook_message, payload)

    # 4. Return immediately (WhatsApp gets 200 OK within ~100ms)
    return {"status": "received"}


async def process_webhook_message(params: dict[str, Any]) -> None:
    """Process WAHA webhook message in background."""
    try:
        message = whatsapp_parser.parse_waha_webhook(params)
        if message:
            await _route_webhook_message(message)
    except Exception as e:
        await _handle_webhook_error(e, params)
```

**Timeline:**

```text
User sends message → WhatsApp → WAHA → Webhook endpoint
                         ↓
                    [Validate: 10ms]
                         ↓
                    [Add to background: 1ms]
                         ↓
                    Return 200 OK to WhatsApp (total: ~100ms)

                    [Background task starts...]
                         ↓
                    [Duplicate check: 50ms]
                         ↓
                    [User lookup: 100ms]
                         ↓
                    [Agent execution: 5-30s]
                         ↓
                    [Service calls: 500ms]
                         ↓
                    [Database writes: 100ms]
                         ↓
                     [Send WhatsApp response: 500ms]
                     [Total background: 6-32s]
```text

## Idempotency

**Rule:** Check `processed_messages` to prevent double-replies and duplicate operations.

**Rationale:**

- WhatsApp may retry webhooks on timeout
- Duplicate processing causes data corruption
- Users get confusing multiple responses

**Implementation:**

```python
# src/interface/webhook.py

async def _check_duplicate_message(message_id: str) -> bool:
    """Check if message has already been processed."""
    existing_log = await db_client.get_first_record(
        collection="processed_messages",
        filter_query=f'message_id = "{sanitize_param(message_id)}"',
    )
    if existing_log:
        logger.info("Message %s already processed, skipping", message_id)
        return True
    return False


async def _handle_text_message(message: whatsapp_parser.ParsedMessage) -> None:
    """Handle text messages through the agent."""
    # 1. Check for duplicate BEFORE processing
    if await _check_duplicate_message(message.message_id):
        return

    # 2. Log processing start
    await _log_message_start(message, "Processing")

    # 3. Process message
    db = db_client.get_client()
    deps = await choresir_agent.build_deps(db=db, user_phone=message.from_phone)
    success, error = await _handle_user_status(
        user_record=user_record,
        message=message,
        db=db,
        deps=deps,
    )

    # 4. Update processing status
    await _update_message_status(
        message_id=message.message_id,
        success=success,
        error=error,
    )
```

**`processed_messages` collection:**

```python
# Schema in src/core/schema.py

"processed_messages": {
    "name": "processed_messages",
    "type": "base",
    "fields": [
        {"name": "message_id", "type": "text", "required": True},
        {"name": "from_phone", "type": "text", "required": True},
        {"name": "processed_at", "type": "date", "required": True},
        {"name": "success", "type": "bool", "required": False},
        {"name": "error_message", "type": "text", "required": False},
    ],
    "indexes": ["CREATE UNIQUE INDEX idx_message_id ON processed_messages (message_id)"],
},
```

## Rate Limiting

Two levels of rate limiting prevent abuse and API overuse:

### Global Webhook Rate Limiting

Protects the webhook endpoint from flood attacks.

```python
# src/interface/webhook.py

@router.post("")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    # 1. Check global rate limit (raises HTTPException directly)
    await rate_limiter.check_webhook_rate_limit()

    # 2. Process message...
```

### Per-User Agent Call Rate Limiting

Prevents individual users from spamming the LLM API (cost control).

```python
# src/interface/webhook.py

async def _handle_user_status(
    *,
    user_record: dict[str, Any],
    message: whatsapp_parser.ParsedMessage,
    db: PocketBase,
    deps: Deps,
) -> tuple[bool, str | None]:
    status = user_record["status"]

    if status == UserStatus.ACTIVE:
        # Check per-user rate limit
        try:
            await rate_limiter.check_agent_rate_limit(message.from_phone)
        except HTTPException as e:
            # Extract rate limit info from headers
            retry_after = e.headers.get("Retry-After", "3600") if e.headers else "3600"
            limit = e.headers.get("X-RateLimit-Limit", "unknown") if e.headers else "unknown"

            response = (
                f"You've reached your hourly limit of {limit} messages. "
                f"Please try again in {int(retry_after) // 60} minutes."
            )
            result = await whatsapp_sender.send_text_message(
                to_phone=message.from_phone,
                text=response,
            )
            return (result.success, result.error)

        # Continue processing...
```

**Rate limiter implementation:**

```python
# src/core/rate_limiter.py

import time
from datetime import datetime, timedelta
from typing import TypedDict
from pocketbase import PocketBase


class RateLimitConfig(TypedDict):
    """Rate limit configuration."""
    max_requests: int
    window_seconds: int


class RateLimiter:
    """Rate limiter using PocketBase for distributed storage."""

    GLOBAL_WEBHOOK_LIMIT: RateLimitConfig = {"max_requests": 100, "window_seconds": 60}
    AGENT_PER_USER_LIMIT: RateLimitConfig = {"max_requests": 20, "window_seconds": 3600}

    async def check_webhook_rate_limit(self) -> None:
        """Check global webhook rate limit."""
        # Implementation using PocketBase for distributed storage
        ...

    async def check_agent_rate_limit(self, phone: str) -> None:
        """Check per-user agent call rate limit."""
        # Implementation using PocketBase for distributed storage
        ...
```

## Scheduled Jobs (APScheduler)

Background jobs run on schedules (CRON) for maintenance tasks.

**Implementation:**

```python
# src/core/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """Start the APScheduler."""
    scheduler.start()


def stop_scheduler() -> None:
    """Stop the APScheduler."""
    scheduler.shutdown()


def add_job(
    func: Callable[[], Awaitable[None]],
    job_id: str,
    cron: str,
) -> None:
    """Add a scheduled job."""
    scheduler.add_job(
        func,
        "cron",
        id=job_id,
        **_parse_cron(cron),
    )
```

**Jobs defined in main.py:**

- `overdue_reminders`: Send reminders for overdue chores
- `daily_report`: Send daily chore summary
- `weekly_leaderboard`: Send weekly leaderboard
- `personal_chore_reminders`: Remind users of personal chores
- `auto_verify_personal`: Auto-verify self-verified personal chores after 24h

**Job execution:**

```python
# src/services/chore_service.py

async def send_overdue_reminders() -> None:
    """Send reminders for overdue chores."""
    # Query overdue chores
    now = datetime.now()
    overdue_chores = await db_client.list_records(
        collection="chores",
        filter_query=f'current_state = "TODO" && deadline < "{now.isoformat()}"',
    )

    # Send reminders
    for chore in overdue_chores:
        await whatsapp_sender.send_text_message(
            to_phone=chore["assigned_to"]["phone"],
            text=f"Reminder: '{chore['title']}' is overdue!",
        )
```

**Scheduler configuration in main.py:**

```python
# src/main.py

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Startup
    configure_logfire()
    await validate_startup_configuration()
    instrument_pydantic_ai()
    await sync_schema(...)
    start_scheduler()  # Start APScheduler
    yield
    # Shutdown
    stop_scheduler()  # Stop APScheduler
```

## Concurrency Safety

### Thread-Safe Configuration

Settings are loaded once at startup via `pydantic-settings` and are immutable.

```python
# src/core/config.py

class Settings(BaseSettings):
    pocketbase_url: str
    openrouter_api_key: str

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra env vars

settings = Settings()  # Loaded once, immutable
```

### Database Client Pooling

The `PocketBaseConnectionPool` handles concurrent access safely:

```python
# src/core/db_client.py

class PocketBaseConnectionPool:
    def __init__(self, ...) -> None:
        self._client: PocketBase | None = None  # Single client (PocketBase is thread-safe)
        self._created_at: datetime | None = None

    def get_client(self) -> PocketBase:
        """Get a healthy PocketBase client instance (thread-safe)."""
        # PocketBase SDK is thread-safe, so we can share a single client
        # Health check and reconnection logic is atomic
        if self._is_connection_expired():
            self._client = None
        if self._client is None:
            return self._get_client_with_retry()
        if not self._health_check(self._client):
            self._client = None
            return self._get_client_with_retry()
        return self._client
```

### Async Task Safety

FastAPI `BackgroundTasks` are executed in the event loop, so they're inherently async-safe.

**No shared state:** All state is in PocketBase (database), not in memory.

```python
# No in-memory caches that could have race conditions
# All state queries go to database (safe under concurrent access)
async def get_chores(*, user_id: str) -> list[dict[str, Any]]:
    return await db_client.list_records(
        collection="chores",
        filter_query=f'assigned_to = "{sanitize_param(user_id)}"',
    )
```

## Error Handling in Async Context

**Rule:** Catch exceptions in background tasks and log them.

```python
# src/interface/webhook.py

async def process_webhook_message(params: dict[str, Any]) -> None:
    """Process WAHA webhook message in background."""
    try:
        message = whatsapp_parser.parse_waha_webhook(params)
        if message:
            await _route_webhook_message(message)
    except Exception as e:
        # Catch all exceptions in background task
        await _handle_webhook_error(e, params)
```

**Error handler:**

```python
async def _handle_webhook_error(e: Exception, params: dict[str, Any]) -> None:
    """Handle errors during webhook processing."""
    logger.error("Error processing webhook message: %s", e)

    error_category, _ = classify_agent_error(e)

    # Notify admins for critical errors
    if admin_notifier.should_notify_admins(error_category):
        try:
            await admin_notifier.notify_admins(
                message=f"⚠️ Webhook error: {error_category.value}\nError: {e}",
                severity="critical",
            )
        except Exception as notify_error:
            logger.error("Failed to notify admins: %s", notify_error)

    # Send user-friendly error message
    try:
        parsed_message = whatsapp_parser.parse_waha_webhook(params)
        if parsed_message and parsed_message.from_phone:
            error_response = classify_error_with_response(e)
            await whatsapp_sender.send_text_message(
                to_phone=parsed_message.from_phone,
                text=f"{error_response.message}\n\n{error_response.suggestion}",
            )
    except Exception as send_error:
        logger.error("Failed to send error message: %s", send_error)
```
