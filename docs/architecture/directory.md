# Directory Structure

This page describes the directory structure and purpose of each directory.

## Layout

All logic must reside in `src/`.

```text
src/
├── agents/              # Pydantic AI Agents (Logic, Tools, Prompts)
│   ├── tools/          # Tool functions that agents can call
│   ├── base.py         # Deps dataclass for dependency injection
│   ├── agent_instance.py # Singleton agent instance
│   ├── choresir_agent.py # Main agent implementation
│   └── retry_handler.py # Agent execution retry logic
├── core/               # Configuration, Logging, Schema, DB Client
│   ├── config.py       # Settings and configuration
│   ├── logging.py      # Logfire integration and logging setup
│   ├── schema.py      # PocketBase schema definitions (code-first)
│   ├── db_client.py   # PocketBase client wrapper with connection pooling
│   ├── errors.py      # Error classification and handling
│   ├── scheduler.py   # APScheduler for cron jobs
│   ├── redis_client.py # Redis client for rate limiting
│   ├── rate_limiter.py # Rate limiting logic
│   ├── recurrence_parser.py # Parse recurrence strings to CRON
│   └── admin_notifier.py # Admin notification for critical errors
├── domain/             # Pydantic DTOs / Entities
│   ├── user.py        # User data model
│   ├── chore.py       # Chore data model and enums
│   ├── pantry.py      # Pantry item data model
│   └── log.py        # Log/audit trail model
├── interface/         # FastAPI Routers & WhatsApp Adapters
│   ├── webhook.py     # Main webhook endpoint
│   ├── webhook_security.py # Security validation (timestamp, nonce)
│   ├── whatsapp_parser.py # Parse WAHA webhook payloads
│   └── whatsapp_sender.py # Send messages to WhatsApp
├── services/         # Functional Business Logic
│   ├── chore_service.py # Chore CRUD and state machine
│   ├── chore_state_machine.py # Chore state transitions
│   ├── user_service.py # User management and join requests
│   ├── verification_service.py # Chore verification workflow
│   ├── pantry_service.py # Pantry and shopping list management
│   ├── analytics_service.py # Stats and leaderboard calculations
│   ├── personal_chore_service.py # Private chore management
│   ├── personal_verification_service.py # Personal chore verification
│   ├── conflict_service.py # Conflict resolution
│   ├── notification_service.py # Notification dispatch
│   ├── session_service.py # Join session management
│   └── robin_hood_service.py # Robin Hood swap logic
├── models/            # Service request/response models
│   └── service_models.py # Pydantic models for service layer
└── main.py           # Application Entrypoint
```

## Directory Purposes

### `agents/`

Contains Pydantic AI agent implementations with logic, tools, and prompts.

**Key Files:**

- `base.py`: Defines the `Deps` dataclass injected into all agent runs via `RunContext[Deps]`
- `agent_instance.py`: Singleton pattern for lazy agent initialization
- `choresir_agent.py`: Main agent orchestrator with system prompt and retry logic
- `retry_handler.py`: Exponential backoff for transient LLM failures

**Subdirectory `tools/`:**
Each tool file contains functions that agents can call. Tools must:

- Take a single Pydantic Model argument (or named args with Pydantic types)
- Return descriptive error strings (not raise exceptions)
- Use injected `Deps` for database access and user context

### `core/`

Contains core application components that provide infrastructure services.

**Key Responsibilities:**

- `config.py`: Load environment variables via `pydantic-settings`
- `logging.py`: Configure Logfire integration, instrument FastAPI and Pydantic AI
- `schema.py`: Code-first PocketBase schema sync on startup
- `db_client.py`: Connection pooling, health checks, CRUD wrapper functions
- `scheduler.py`: APScheduler configuration for background jobs
- `redis_client.py`: Redis client wrapper (optional, degrades gracefully if unavailable)
- `rate_limiter.py`: Global webhook and per-user rate limiting

### `domain/`

Contains Pydantic DTOs (Data Transfer Objects) and domain entities.

**Key Responsibilities:**

- Define data models for type safety and validation
- Encode business rules in validators
- Provide clear interfaces between layers

**Examples:**

- `ChoreState` enum: Valid chore states (TODO, PENDING_VERIFICATION, etc.)
- `Chore` model: Chore entity with typed fields
- `User` model: User entity with validation rules

### `interface/`

Contains FastAPI routers and WhatsApp adapters for external communication.

**Key Responsibilities:**

- Receive and validate webhook requests
- Parse WhatsApp message payloads
- Send responses back to WhatsApp
- Implement security checks (timestamp validation, nonce, rate limiting)

**Key Pattern:**
Webhook endpoint returns `200 OK` immediately, then dispatches processing to background tasks.

### `services/`

Contains functional business logic using standalone functions (not service classes).

**Key Pattern:**
All services are functional modules with exported functions, not classes with methods.

**Example:**

```python
# src/services/chore_service.py

async def create_chore(*, title: str, recurrence: str) -> dict[str, Any]:
    """Create a new chore."""
    schedule_cron = parse_recurrence_to_cron(recurrence)
    deadline = _calculate_next_deadline(schedule_cron)
    return await db_client.create_record(collection="chores", data={...})

async def get_chores(*, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get chores with optional filters."""
    ...
```

**Why functional?**

- Easier to test (no hidden state, easy to mock dependencies)
- Simpler to reason about (explicit inputs/outputs)
- Avoids dependency injection frameworks

### `models/`

Contains Pydantic models for service request/response DTOs.

**Key Responsibilities:**

- Define typed interfaces between service layers
- Validation of service inputs/outputs

### `main.py`

Application entrypoint with FastAPI app configuration.

**Key Responsibilities:**

- Configure FastAPI app with lifespan
- Register routers
- Startup validation (credentials, connectivity)
- Schema sync on startup
- Health check endpoints

## Dependencies Between Layers

```text
interface → agents → services → db_client → PocketBase
                ↓
              domain
```

**Upward dependencies:**

- Interface calls agents (or services directly for button clicks)
- Agents call services via tools
- Services call db_client for data access
- Services use domain models for validation
- Everything depends on core (config, logging, errors)

**No downward dependencies:**

- Services never call agents
- Services never call interface
- db_client never calls services
