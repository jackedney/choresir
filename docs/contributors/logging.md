# Logging & Observability

This page describes logging patterns and observability in WhatsApp Home Boss.

## Standard Logging Pattern

Use Python's standard `logging` module in all files.

### Module-Level Setup

Always include at the top of every file:

```python
import logging

logger = logging.getLogger(__name__)
```

**Why `__name__`?**

- Creates a logger hierarchy based on module path
- Enables filtering by module/package
- Follows Python logging best practices

### Logfire Integration

Logfire automatically captures all standard logging calls via `logfire.instrument_logging()` configured in `src/core/logging.py`.

**What this means:**

- No need to use `logfire.info()`, `logfire.error()`, etc. directly
- All standard `logger.info()`, `logger.error()` calls are captured
- Centralized logging configuration
- Automatic structured data capture

**Never use direct logfire calls in application code.**

```python
# BAD: Direct logfire call (avoids standard logging)
import logfire

logfire.info("User action", user_id="123")

# GOOD: Standard logging (automatically captured by Logfire)
import logging

logger = logging.getLogger(__name__)
logger.info("User action", extra={"user_id": "123"})
```

## Structured Logging

Use the `extra` parameter for structured data:

```python
logger.info("User action", extra={"user_id": "123", "action": "claim_chore"})
```

### Logging Utilities

Use helpers from `src/core/logging.py` for common patterns:

```python
from src.core.logging import log_with_user_context

log_with_user_context(logger, "info", "Action performed", user_id="123", action="claim")
```

This helper automatically adds common context fields (user_id, timestamp, etc.).

## Log Levels

### DEBUG

**Use for:** Fine-grained diagnostic info

- Cache hits and misses
- Internal state changes
- Detailed execution flow
- Variable values for troubleshooting

```python
logger.debug("Cache hit for key %s", cache_key)
logger.debug("Processing step 3 of 5: %s", step_result)
```

### INFO

**Use for:** General operational events

- User actions (e.g., user claims a chore)
- Job execution (e.g., daily report sent)
- Configuration changes
- Successful operations

```python
logger.info("User claimed chore", extra={"user_id": "123", "chore_id": "456"})
logger.info("Daily report sent successfully", extra={"recipients": 5})
```

### WARNING

**Use for:** Recoverable issues

- Failed retries (but operation eventually succeeded)
- Degraded performance (slower than expected but functional)
- Missing optional features (e.g., Redis unavailable)
- Deprecated usage

```python
logger.warning(
    "Redis connection failed, using in-memory fallback",
    extra={"error": str(e)},
)
logger.warning(
    "Response time exceeded threshold",
    extra={"duration_ms": 5000, "threshold_ms": 3000},
)
```

### ERROR

**Use for:** Failures requiring attention

- Database errors
- API failures
- Validation errors that prevent operation
- Unhandled exceptions in background tasks

```python
logger.error(
    "Failed to create chore",
    exc_info=True,
    extra={"user_id": "123", "error": str(e)},
)
```

**Note:** Use `exc_info=True` to include stack trace when catching exceptions.

### CRITICAL

**Use for:** System-threatening failures

- Startup failures
- Data corruption
- Service unavailability
- Security breaches

```python
logger.critical(
    "PocketBase connection failed on startup",
    exc_info=True,
    extra={"url": settings.pocketbase_url},
)
```

## Best Practices

### Consistent Context

Include relevant context fields for filtering and debugging:

```python
# Good: Include context
logger.info(
    "Chore completed",
    extra={
        "chore_id": "abc123",
        "user_id": "user456",
        "completion_time": datetime.now().isoformat(),
    },
)

# Bad: Missing context
logger.info("Chore completed")
```

**Common context fields:**

- `user_id`: User performing action
- `request_id`: Unique request identifier
- `operation_type`: Type of operation (create, update, delete)
- `duration_ms`: Operation duration (for performance)
- `error`: Error message (for errors)

### No Sensitive Data

Never log passwords, tokens, or personal information:

```python
# BAD: Logging sensitive data
logger.info("User logged in", extra={"password": user_password})

# BAD: Logging full phone numbers
logger.info("User action", extra={"phone": "+1234567890"})

# GOOD: Log identifiers only
logger.info("User logged in", extra={"user_id": user_id})

# GOOD: Anonymize phone numbers
logger.info(
    "User action",
    extra={"phone_anonymous": phone[-4:]}  # Only last 4 digits
)
```

### Actionable Messages

Log messages should be clear and actionable:

```python
# BAD: Vague message
logger.info("Something happened")

# BAD: Too much implementation detail
logger.info("Invoking db_client.create_record with collection=chores and data={'title': 'Dishes'}")

# GOOD: Actionable, clear message
logger.info("Chore created", extra={"chore_id": "abc123", "title": "Dishes"})
```

## Logging in Services

### Service Function Pattern

```python
import logging

logger = logging.getLogger(__name__)

async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    """Create a new chore."""
    try:
        schedule_cron = parse_recurrence_to_cron(recurrence)
        logger.debug(
            "Parsed recurrence to CRON",
            extra={"recurrence": recurrence, "cron": schedule_cron},
        )

        deadline = _calculate_next_deadline(schedule_cron)
        logger.debug("Calculated deadline", extra={"deadline": deadline.isoformat()})

        chore_data = {
            "title": title,
            "schedule_cron": schedule_cron,
            "assigned_to": "",
            "current_state": ChoreState.TODO,
            "deadline": deadline.isoformat(),
        }

        result = await db_client.create_record(collection="chores", data=chore_data)
        logger.info(
            "Chore created",
            extra={"chore_id": result["id"], "title": title},
        )
        return result

    except Exception as e:
        logger.error(
            "Failed to create chore",
            exc_info=True,
            extra={"title": title, "error": str(e)},
        )
        raise
```

## Logging in Background Tasks

Background tasks must handle errors and log them:

```python
async def process_webhook_message(params: dict[str, Any]) -> None:
    """Process WAHA webhook message in background."""
    try:
        message = whatsapp_parser.parse_waha_webhook(params)
        if message:
            logger.info(
                "Processing webhook message",
                extra={"message_id": message.message_id, "from": message.from_phone},
            )
            await _route_webhook_message(message)

    except Exception as e:
        # Catch all exceptions in background task
        logger.error(
            "Error processing webhook message",
            exc_info=True,
            extra={"params": params},
        )
        await _handle_webhook_error(e, params)
```

## Logging in Agents

Agents should log tool calls and results:

```python
async def tool_log_chore(ctx: RunContext[Deps], params: LogChoreParams) -> str:
    """Log a chore completion."""
    deps = ctx.deps

    logger.info(
        "Tool called: log_chore",
        extra={
            "user_id": deps.user_id,
            "chore_id": params.chore_id,
        },
    )

    try:
        await chore_service.log_completion(
            chore_id=params.chore_id,
            user_id=deps.user_id,
        )
        logger.info(
            "Chore logged successfully",
            extra={"chore_id": params.chore_id},
        )
        return "Chore logged successfully"

    except Exception as e:
        logger.error(
            "Tool failed: log_chore",
            exc_info=True,
            extra={"chore_id": params.chore_id, "error": str(e)},
        )
        return f"Error: Failed to log chore - {e}"
```

## Performance Logging

Track performance of critical operations:

```python
import time
from datetime import datetime, timedelta

async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    """Create a new chore."""
    start_time = time.time()

    try:
        # ... chore creation logic ...

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Chore created",
            extra={
                "chore_id": result["id"],
                "title": title,
                "duration_ms": duration_ms,
            },
        )

        return result

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Failed to create chore",
            exc_info=True,
            extra={
                "title": title,
                "duration_ms": duration_ms,
                "error": str(e),
            },
        )
        raise
```

## Error Classification

Use structured logging with error types:

```python
from src.core.errors import classify_agent_error

async def _handle_webhook_error(e: Exception, params: dict[str, Any]) -> None:
    """Handle errors during webhook processing."""
    error_category, is_retryable = classify_agent_error(e)

    logger.error(
        "Webhook processing error",
        exc_info=True,
        extra={
            "error_category": error_category.value,
            "is_retryable": is_retryable,
            "params": params,
        },
    )
```

## Observability Tools

### Logfire Dashboard

- View all logs in real-time
- Filter by module, level, or context
- Trace requests end-to-end
- Monitor error rates and performance

### Structured Queries

Use context fields to filter logs:

```bash
# View all actions by a specific user
logger.info.filter(user_id="user123")

# View all errors in a specific module
logger.error.filter(module="src.services.chore_service")

# View all slow operations
logger.info.filter(duration_ms__gt=5000)
```

## Common Logging Pitfalls

### Don't Log in Loops

```python
# BAD: Logging every iteration
for chore in chores:
    logger.info("Processing chore", extra={"chore_id": chore["id"]})

# GOOD: Log summary
logger.info(
    "Processed chores",
    extra={"count": len(chores), "duration_ms": total_duration_ms},
)
```

### Don't Over-Log

```python
# BAD: Too much noise
logger.debug("Variable x = %s", x)
logger.debug("Variable y = %s", y)
logger.debug("Variable z = %s", z)

# GOOD: Meaningful events
logger.debug("Calculated coordinates", extra={"x": x, "y": y, "z": z})
```

### Don't Log After Exception

```python
# BAD: Logging after exception (won't execute)
try:
    await risky_operation()
except Exception as e:
    raise ValueError("Failed")  # logger.error() here would be unreachable

# GOOD: Log before raising
try:
    await risky_operation()
except Exception as e:
    logger.error("Operation failed", exc_info=True)
    raise ValueError("Failed") from e
```

## Further Reading

- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)
- [Logfire Documentation](https://pydanticlogfire.com/)
- [Architecture: Async & Concurrency](../architecture/async.md)
