# Database Patterns

This page describes database interaction patterns in WhatsApp Home Boss.

## Access

Use the official `pocketbase` Python SDK via the wrapper functions in `src/core/db_client.py`.

## Encapsulation

**Rule:** Never import the PocketBase client directly into Routers or Agents. Always use `src/core.db_client` functions.

**Rationale:**

- Centralized connection management (pooling, health checks)
- Consistent error handling
- Easier to mock for testing
- Single point for database configuration

**Example (Correct):**

```python
# src/services/chore_service.py

from src.core import db_client

async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    """Create a new chore."""
    chore_data = {
        "title": title,
        "schedule_cron": parse_recurrence_to_cron(recurrence),
        "current_state": ChoreState.TODO,
    }
    return await db_client.create_record(collection="chores", data=chore_data)
```

**Negative Case (Avoid):**

```python
# AVOID: Direct PocketBase client import

from pocketbase import PocketBase

async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    client = PocketBase(settings.pocketbase_url)  # Wrong!
    client.admins.auth_with_password(...)  # Wrong!
    # ...
```

## Database Client API

The `src/core/db_client.py` module provides async wrapper functions:

### `create_record`

Create a new record in a collection.

```python
from src.core import db_client

record = await db_client.create_record(
    collection="chores",
    data={
        "title": "Wash Dishes",
        "schedule_cron": "0 20 * * *",
        "assigned_to": "user_id",
        "current_state": "TODO",
    },
)
# Returns: {"id": "abc123", "title": "Wash Dishes", ...}
```

### `get_record`

Get a record by ID.

```python
chore = await db_client.get_record(
    collection="chores",
    record_id="abc123",
)
# Returns: {"id": "abc123", "title": "Wash Dishes", ...}
# Raises: KeyError if not found
```

### `update_record`

Update an existing record.

```python
updated = await db_client.update_record(
    collection="chores",
    record_id="abc123",
    data={"current_state": "COMPLETED"},
)
# Returns: {"id": "abc123", "current_state": "COMPLETED", ...}
# Raises: KeyError if not found
```

### `delete_record`

Delete a record.

```python
await db_client.delete_record(
    collection="chores",
    record_id="abc123",
)
# Raises: KeyError if not found
```

### `list_records`

List records with filtering, sorting, and pagination.

```python
chores = await db_client.list_records(
    collection="chores",
    page=1,
    per_page=50,
    filter_query='current_state = "TODO" && assigned_to = "user123"',
    sort="+deadline",  # Ascending by deadline
)
# Returns: [{"id": "abc123", ...}, {"id": "def456", ...}]
```

### `get_first_record`

Get first matching record or `None` if not found.

```python
user = await db_client.get_first_record(
    collection="users",
    filter_query=f'phone = "{sanitize_param("+1234567890")}"',
)
# Returns: {"id": "user123", "phone": "+1234567890", ...}
# Returns: None if not found (no exception)
```

### `get_client`

Get a healthy PocketBase client (used by agents that need direct access).

```python
from src.core.db_client import get_client

client = get_client()
# Returns authenticated PocketBase client from connection pool
```

## Connection Pooling

The `PocketBaseConnectionPool` class manages database connections with:

- **Automatic reconnection** when connection lifetime expires (default: 1 hour)
- **Health checks** before returning a client
- **Exponential backoff retry** (1s, 2s, 4s delays) on connection failures
- **Single global instance** shared across the application

**Implementation:**

```python
# src/core/db_client.py

class PocketBaseConnectionPool:
    def get_client(self) -> PocketBase:
        """Get a healthy PocketBase client instance."""
        if self._is_connection_expired():
            self._client = None
        if self._client is None:
            return self._get_client_with_retry()
        if not self._health_check(self._client):
            self._client = None
            return self._get_client_with_retry()
        return self._client
```

## Filter Query Syntax

PocketBase uses a custom filter syntax. Always sanitize user input.

**Basic comparisons:**

```python
filter_query = 'current_state = "TODO"'
filter_query = 'deadline > "2024-01-01"'
filter_query = 'assigned_to = ""'  # Empty string for unassigned
```

**Logical operators:**

```python
filter_query = 'current_state = "TODO" && assigned_to = "user123"'
filter_query = 'current_state = "TODO" || current_state = "PENDING_VERIFICATION"'
```

**Sanitizing user input:**

```python
from src.core.db_client import sanitize_param

# ALWAYS sanitize user input in filter queries
user_phone = sanitize_param(user_input_phone)
filter_query = f'phone = "{user_phone}"'
```

**Negative Case (Vulnerable):**

```python
# AVOID: Direct interpolation (injection vulnerability)

filter_query = f'phone = "{user_input_phone}"'  # VULNERABLE!
# If user_phone is: "+12345" || true || "
# Results in: phone = "+12345" || true || ""  (bypasses filter!)
```

## Schema Management (Code-First Approach)

**Rule:** Define database schema in code, not via PocketBase Admin UI.

**Location:** `src/core/schema.py` defines all collections, fields, and indexes.

**Schema sync:** The `sync_schema()` function is called on application startup to:

1. Create collections that don't exist
2. Add missing fields to existing collections
3. Update field definitions to match code
4. Create database indexes

**Example schema:**

```python
# src/core/schema.py

def _get_collection_schema(*, collection_name: str) -> dict[str, Any]:
    schemas = {
        "chores": {
            "name": "chores",
            "type": "base",
            "fields": [
                {"name": "title", "type": "text", "required": True},
                {"name": "schedule_cron", "type": "text", "required": True},
                {
                    "name": "assigned_to",
                    "type": "relation",
                    "required": True,
                    "collectionId": "users",
                    "maxSelect": 1,
                },
                {
                    "name": "current_state",
                    "type": "select",
                    "required": True,
                    "values": ["TODO", "PENDING_VERIFICATION", "COMPLETED", "CONFLICT", "DEADLOCK"],
                    "maxSelect": 1,
                },
                {"name": "deadline", "type": "date", "required": True},
            ],
            "indexes": ["CREATE INDEX idx_deadline ON chores (deadline)"],
        },
    }
    return schemas[collection_name]
```

**Collections defined:**

- `users`: Household members
- `chores`: Household chores
- `logs`: Chore completion logs
- `robin_hood_swaps`: Weekly swap tracking
- `processed_messages`: Idempotency tracking
- `pantry_items`: Pantry inventory
- `shopping_list`: Shopping list
- `personal_chores`: Private chores
- `personal_chore_logs`: Private chore logs
- `join_sessions`: Onboarding flow state

## Admin Authentication

The application uses PocketBase admin authentication for all database operations.

**Reason:**

- Simplified security model (no per-user auth needed)
- Backend has full control over data
- Consistent with household admin role system

**Configuration:**

```python
# src/core/config.py

class Settings(BaseSettings):
    pocketbase_url: str
    pocketbase_admin_email: str
    pocketbase_admin_password: str
```

**Authentication in db_client.py:**

```python
def _create_client(self) -> PocketBase:
    """Create and authenticate a new PocketBase client."""
    client = PocketBase(self._url)
    client.admins.auth_with_password(self._admin_email, self._admin_password)
    return client
```

## Transaction Support

PocketBase does not support multi-document transactions. Workarounds:

**1. Idempotency:** Check state before modifying (e.g., check chore state before transition)

```python
chore = await db_client.get_record(collection="chores", record_id=chore_id)
if chore["current_state"] != expected_state:
    raise ValueError(f"Chore is in {chore['current_state']}, not {expected_state}")
```

**2. Audit logs:** Track all operations in `logs` collection for reconciliation

```python
await db_client.create_record(
    collection="logs",
    data={
        "chore_id": chore_id,
        "user_id": user_id,
        "action": "VERIFIED",
        "timestamp": datetime.now().isoformat(),
    },
)
```

**3. Idempotency keys:** Track processed messages to prevent double-processing

```python
# Check if message already processed
existing = await db_client.get_first_record(
    collection="processed_messages",
    filter_query=f'message_id = "{sanitize_param(message_id)}"',
)
if existing:
    return  # Skip duplicate
```
