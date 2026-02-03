# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      External Systems                           │
│  WhatsApp (WAHA)              OpenRouter (LLM)                 │
└─────────┬───────────────────────────┬───────────────────────────┘
          │ Webhook                   │ API
          ▼                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Interface Layer (src/interface/)                               │
│  - webhook.py: Receive POST, validate, return 200 immediately   │
│  - whatsapp_parser.py: Parse WAHA payloads                      │
│  - whatsapp_sender.py: Send responses                           │
└─────────────────────────────────────────────────────────────────┘
          │ BackgroundTask
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Agent Layer (src/agents/)                                      │
│  - choresir_agent.py: Main agent with system prompt             │
│  - tools/*.py: Tool functions the LLM can call                  │
│  - base.py: Deps dataclass for dependency injection             │
└─────────────────────────────────────────────────────────────────┘
          │ Tool calls
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Service Layer (src/services/)                                  │
│  - Functional modules (not classes)                             │
│  - chore_service, user_service, verification_service, etc.      │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Infrastructure (src/core/)                                     │
│  - db_client.py: PocketBase wrapper with connection pooling     │
│  - config.py: Settings via pydantic-settings                    │
│  - scheduler.py: APScheduler for cron jobs                      │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
src/
├── agents/           # Pydantic AI agent + tools
│   ├── tools/        # Tool functions (tool_log_chore, etc.)
│   ├── base.py       # Deps dataclass
│   └── choresir_agent.py
├── core/             # Infrastructure
│   ├── config.py     # Environment settings
│   ├── db_client.py  # PocketBase CRUD + pooling
│   ├── schema.py     # Code-first DB schema
│   └── scheduler.py  # Background jobs
├── domain/           # Pydantic DTOs
├── interface/        # FastAPI routes + WhatsApp adapters
├── services/         # Business logic (functional)
└── main.py
```

## Key Patterns

### Functional Services

Use standalone functions, not service classes:

```python
# Good
async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    return await db_client.create_record(collection="chores", data={...})

# Avoid
class ChoreService:
    def __init__(self, db): ...
```

### Keyword-Only Arguments

Enforce `*` for functions with >2 parameters:

```python
def create_task(*, name: str, due: datetime, user: str) -> dict[str, Any]: ...
```

### DTOs Only

Use Pydantic models between layers, never raw dicts:

```python
class Chore(BaseModel):
    id: str
    title: str
    current_state: ChoreState
```

### No Custom Exceptions

Use `ValueError`, `KeyError`, `HTTPException`. No custom exception hierarchies.

### Strict Typing

All arguments and returns must be typed, including `-> None`.

### Dependency Injection

Use `RunContext[Deps]` in tools, never global state:

```python
@dataclass
class Deps:
    db: PocketBase
    user_id: str
    user_phone: str
    user_name: str
    user_role: str
    current_time: datetime

async def tool_log_chore(ctx: RunContext[Deps], params: LogChore) -> str:
    user_id = ctx.deps.user_id  # Access via context
```

### Sanitize DB Params

Always use `sanitize_param()` for user input in PocketBase filters:

```python
filter_query = f'phone = "{sanitize_param(user_phone)}"'
```

## Database

### Access Pattern

Always use `src/core/db_client` functions, never import PocketBase directly:

```python
from src.core import db_client

record = await db_client.create_record(collection="chores", data={...})
records = await db_client.list_records(collection="chores", filter_query="...")
```

### Collections

`users`, `chores`, `logs`, `processed_messages`, `pantry_items`, `shopping_list`, `personal_chores`, `personal_chore_logs`, `join_sessions`, `robin_hood_swaps`

### Schema Sync

Schema is defined in `src/core/schema.py` and synced on startup. No manual DB migrations.

## Async & Background Tasks

Webhooks return `200 OK` immediately, then process in background:

```python
@router.post("")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    background_tasks.add_task(process_webhook_message, payload)
    return {"status": "received"}  # Returns in ~100ms
```

AI processing happens in background (5-30s). Idempotency via `processed_messages` collection prevents duplicate handling.
