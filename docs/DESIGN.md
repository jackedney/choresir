# Design Document

## Architecture

Choresir is a single-process, self-hosted Python application with three main components connected via internal interfaces:

```
WhatsApp Group Chat
        |
        v
  [WAHA Container] <-- Docker, self-hosted
        |
        | webhooks (HTTP POST)
        v
  [FastAPI Application]
        |
        +-- Webhook Handler --> SQLite Job Queue --> Message Worker(s)
        |                                               |
        |                                               v
        |                                         [PydanticAI Agent]
        |                                               |
        |                                               v
        |                                         [LiteLLM + OpenRouter]
        |                                               |
        |                                               v
        |                                         Tool Execution Layer
        |                                               |
        |                                               v
        |                                         [SQLModel / SQLite DB]
        |
        +-- APScheduler (reminders, daily summary, weekly leaderboard)
        |       |
        |       v
        |   [WAHA API] (outbound messages)
        |
        +-- FastHTML Admin Interface
                |
                v
            [SQLModel / SQLite DB]
```

### Component Responsibilities

**Webhook Handler** (SPEC reqs 1, 2, 3, 4, 5, 29)
Receives incoming WhatsApp messages from WAHA, validates webhook authenticity, inserts into the SQLite job queue for async processing, and returns 200 immediately.

**SQLite Job Queue + Message Workers** (SPEC reqs 2, 3, 4, 28, 30)
Durable message processing pipeline. Deduplicates via primary key, enforces global and per-user rate limits (via aiolimiter — a global AsyncLimiter instance alongside a per-user dict), retries with exponential backoff on AI unavailability. Workers run as background coroutines in the FastAPI lifespan.

**AI Agent Layer** (SPEC reqs 1, 6-17)
A PydanticAI agent processes natural language messages. The agent is configured with a dynamic system prompt (base template from disk + household context from DB at runtime) and typed tool functions for task management operations (create, complete, verify, reassign, delete). PydanticAI handles tool schema generation, structured output validation, and conversation flow. LiteLLM provides the provider abstraction to route requests through OpenRouter.

**Task Management Core** (SPEC reqs 6-17)
Domain logic for tasks, verification, recurrence, completion history, and takeovers. Personal task deletion by the owner is immediate; shared task deletion requires peer approval. Accessed by the LLM layer via tool functions and by the scheduler for recurring task resets.

**Scheduler** (SPEC reqs 14, 24, 25, 26, 27)
APScheduler v4 running cron-triggered jobs: overdue task reminders, daily activity summary, weekly leaderboard, and recurring task deadline resets. Sends messages via WAHA API.

**Admin Interface** (SPEC reqs 21, 31)
FastHTML web application mounted alongside the FastAPI app. Provides member management, task management (viewing, editing, deleting), household configuration, and WAHA session setup. Protected by authentication and CSRF.

**Onboarding Flow** (SPEC reqs 18, 19, 20)
Detects new members joining the WhatsApp group via WAHA webhooks, registers them with pending status, and prompts for their name before granting full access.

### Data Flow

1. User sends message in WhatsApp group
2. WAHA receives it and POSTs webhook to FastAPI
3. Webhook handler validates signature, inserts job into `message_jobs` table, returns 200
4. Message worker claims the job, applies rate limiting, invokes the PydanticAI agent
5. Agent assembles system prompt (base template + household context from DB), sends to LLM via LiteLLM/OpenRouter
6. LLM returns tool calls (e.g., `create_task`, `complete_task`); PydanticAI executes them and validates outputs
7. Agent returns final response, sent back to the WhatsApp group via WAHA HTTP API

### Deployment

Single Docker Compose stack with two containers:
- **choresir**: FastAPI application (webhook handler, workers, scheduler, admin)
- **waha**: WAHA WhatsApp HTTP API

Single SQLite database file shared across all components within the choresir container.

## Technology Choices

| Package | Purpose | Serves Requirement | Alternatives Considered |
|---------|---------|-------------------|------------------------|
| FastAPI | HTTP framework, ASGI server | Reqs 1, 2, 5, 29 (webhook handling) | Litestar, Flask |
| WAHA | WhatsApp integration (self-hosted) | Reqs 1, 18 (messaging interface) | Meta Cloud API, Twilio, Baileys |
| PydanticAI | AI agent framework (tools, structured output, prompts) | Reqs 1, 6-17 (agent orchestration, tool calling, validation) | LangChain, raw LiteLLM, manual tool parsing |
| LiteLLM | LLM provider abstraction (via PydanticAI) | Req 28 (provider-agnostic, retry/fallback) | anthropic SDK, openai SDK |
| OpenRouter | LLM provider | Reqs 1, 6-17 (AI model access) | Anthropic direct, OpenAI direct, Ollama |
| SQLModel | ORM (Pydantic + SQLAlchemy) | Req constraint 2 (SQLite data store) | SQLAlchemy, Tortoise ORM, Peewee |
| Alembic | Database migrations | Req constraint 2 (schema management) | Tortoise Aerich, manual SQL |
| APScheduler v4 | Task scheduling (async, cron) | Reqs 14, 24, 25, 26, 27 (reminders, reports, recurrence) | Celery, arq, Huey |
| FastHTML | Admin web interface (pure Python) | Reqs 21, 31 (admin UI, auth, CSRF) | SQLAdmin, Starlette Admin, React SPA |
| httpx | Async HTTP client (WAHA API calls) | Reqs 1, 25, 26, 27 (outbound messages) | aiohttp, requests |
| aiolimiter | Global and per-user async rate limiting | Reqs 4, 30 (rate limits) | Manual token bucket |
| tenacity | Retry/backoff decorator | Req 28 (AI unavailability handling) | Manual retry loops |
| aiosqlite | Async SQLite driver | Req constraint 2 (async DB access) | sqlite3 (sync) |

## Interfaces

### WAHA Webhook Interface (Inbound)

WAHA posts incoming messages to the FastAPI webhook endpoint.

- **Endpoint**: `POST /webhook`
- **Authentication**: Shared secret in header (SPEC req 29)
- **Payload**: JSON with message ID, sender, group ID, message body
- **Response**: `200 OK` (acknowledge before processing, SPEC req 2)

### WAHA HTTP API (Outbound)

The application sends messages back to WhatsApp via WAHA's REST API.

- **Base URL**: Configurable (e.g., `http://waha:3000`)
- **Send message**: `POST /api/sendText` with session, chatId, text
- **Authentication**: WAHA API key in header

### AI Agent Interface

A PydanticAI agent handles all LLM interaction. LiteLLM routes requests through OpenRouter.

- **Agent definition**: `pydantic_ai.Agent` with typed tool functions and structured output models
- **System prompt**: Hybrid — base template loaded from disk + dynamic household context (member names, roles, active tasks) assembled from DB per request via `@agent.system_prompt` decorator
- **Tools defined as**: Decorated Python functions with type-annotated parameters; PydanticAI auto-generates JSON schemas
- **Tool categories**: Task CRUD, verification, assignment, analytics queries
- **Structured output**: Pydantic models validate LLM responses; auto-retry on malformed output
- **Response flow**: Agent runs tool calls, feeds results back to LLM, returns validated natural language response

### Admin Interface

FastHTML application serving the admin web UI.

- **Mount point**: `/admin` (sub-application within FastAPI)
- **Authentication**: Session-based with signed cookies (SPEC req 31)
- **CSRF protection**: Token-based middleware (SPEC req 31)
- **Pages**: Member management, task management (list, edit, delete), household settings (household name, takeover limit per week, reminder/summary schedule times, default verification mode), WAHA session setup

### Internal: Job Queue Contract

The webhook handler and message workers communicate through the `message_jobs` SQLite table.

- **Enqueue**: `INSERT OR IGNORE` with WhatsApp message ID as primary key (dedup)
- **Claim**: Worker updates `status` from `pending` to `processing`
- **Complete**: Worker updates `status` to `done`
- **Retry**: Worker updates `status` back to `pending` with incremented `attempts` and `run_after` delay
- **Fail**: Worker updates `status` to `failed` after max attempts

### Internal: Scheduler to Messaging

APScheduler jobs query the database for relevant data and send messages via WAHA HTTP API.

- **Daily summary** (SPEC req 26): Queries task completion stats, sends to group
- **Weekly leaderboard** (SPEC req 27): Queries rankings, sends to group
- **Overdue reminders** (SPEC req 25): Queries overdue tasks, sends targeted reminders
- **Recurring reset** (SPEC req 14): Queries verified recurring tasks, resets status and calculates next deadline

## Key Decisions

| Decision | Choice | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Application framework | FastAPI | Litestar, Flask | Largest async Python ecosystem, native Starlette ASGI, best integration story with SQLModel and tooling |
| WhatsApp integration | WAHA (self-hosted) | Meta Cloud API, Twilio, Baileys | Fully self-hosted (constraint 4), REST API, free, group chat support, Docker deployment |
| AI agent framework | PydanticAI | LangChain, raw LiteLLM, manual parsing | Type-safe tools via decorators, structured output validation, dynamic prompts, same ecosystem as FastAPI/SQLModel |
| LLM provider abstraction | LiteLLM (via PydanticAI) | Direct provider SDKs | Provider-agnostic, easy model switching, built-in retry/fallback |
| LLM provider | OpenRouter | Anthropic direct, OpenAI direct, Ollama | Single API key for all models, unified billing |
| System prompt management | Hybrid (disk template + DB context) | Hardcoded strings, fully DB-stored | Base prompt is version-controlled and testable; dynamic context keeps agent aware of current household state |
| Database layer | SQLModel + Alembic | SQLAlchemy, Tortoise, Peewee, raw SQL | Pydantic + SQLAlchemy in one model class, native FastAPI fit, minimal boilerplate |
| Task scheduling | APScheduler v4 | Celery, arq, Huey, manual asyncio | Native async cron triggers, zero external deps, single-process compatible |
| Admin interface | FastHTML | SQLAdmin, Starlette Admin, React SPA | Pure Python (no JS/templates), full control over custom pages like WAHA session setup |
| Async processing | SQLite-backed job queue | BackgroundTasks, Redis+arq, asyncio.Queue | Durable (survives restarts), native dedup via PK, retry/backoff via run_after column, no external deps |
| HTTP client | httpx | aiohttp, requests | Async-native, clean API, widely adopted, pairs well with FastAPI |
| Rate limiting | aiolimiter | Manual token bucket, Redis-based | Lightweight async leaky-bucket, zero external deps |
