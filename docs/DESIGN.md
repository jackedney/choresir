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

**SQLite Job Queue + Message Workers** (SPEC reqs 2, 3, 4, 28)
Durable message processing pipeline. Deduplicates via primary key, enforces per-user rate limits, retries with exponential backoff on AI unavailability. Workers run as background coroutines in the FastAPI lifespan.

**LLM Layer** (SPEC reqs 1, 6-17)
Processes natural language messages via LiteLLM calling OpenRouter. Extracts intent and executes structured tool calls for task management operations (create, complete, verify, reassign, delete).

**Task Management Core** (SPEC reqs 6-17)
Domain logic for tasks, verification, recurrence, completion history, and takeovers. Accessed by the LLM layer via tool functions and by the scheduler for recurring task resets.

**Scheduler** (SPEC reqs 14, 24, 25, 26, 27)
APScheduler v4 running cron-triggered jobs: overdue task reminders, daily activity summary, weekly leaderboard, and recurring task deadline resets. Sends messages via WAHA API.

**Admin Interface** (SPEC reqs 21, 31)
FastHTML web application mounted alongside the FastAPI app. Provides member management, household configuration, and WAHA session setup. Protected by authentication and CSRF.

**Onboarding Flow** (SPEC reqs 18, 19, 20)
Detects new members joining the WhatsApp group via WAHA webhooks, registers them with pending status, and prompts for their name before granting full access.

### Data Flow

1. User sends message in WhatsApp group
2. WAHA receives it and POSTs webhook to FastAPI
3. Webhook handler validates signature, inserts job into `message_jobs` table, returns 200
4. Message worker claims the job, applies rate limiting, sends message to LiteLLM
5. LLM returns tool calls (e.g., `create_task`, `complete_task`)
6. Tool execution layer runs the operation against SQLite via SQLModel
7. Response is sent back to the WhatsApp group via WAHA HTTP API

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
| LiteLLM | LLM SDK (provider-agnostic) | Reqs 1, 6-17, 28 (NL processing, retry/fallback) | anthropic SDK, openai SDK |
| OpenRouter | LLM provider | Reqs 1, 6-17 (AI model access) | Anthropic direct, OpenAI direct, Ollama |
| SQLModel | ORM (Pydantic + SQLAlchemy) | Req constraint 2 (SQLite data store) | SQLAlchemy, Tortoise ORM, Peewee |
| Alembic | Database migrations | Req constraint 2 (schema management) | Tortoise Aerich, manual SQL |
| APScheduler v4 | Task scheduling (async, cron) | Reqs 14, 24, 25, 26, 27 (reminders, reports, recurrence) | Celery, arq, Huey |
| FastHTML | Admin web interface (pure Python) | Reqs 21, 31 (admin UI, auth, CSRF) | SQLAdmin, Starlette Admin, React SPA |
| httpx | Async HTTP client (WAHA API calls) | Reqs 1, 25, 26, 27 (outbound messages) | aiohttp, requests |
| aiolimiter | Per-user async rate limiting | Reqs 4, 30 (rate limits) | Manual token bucket |
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

### LLM Tool Interface

LiteLLM calls OpenRouter with a set of tool definitions. The LLM returns structured tool calls that the application executes.

- **Tools defined as**: JSON schema function definitions passed to `litellm.completion()`
- **Tool categories**: Task CRUD, verification, assignment, analytics queries
- **Response format**: Tool call results fed back to LLM for natural language response generation

### Admin Interface

FastHTML application serving the admin web UI.

- **Mount point**: `/admin` (sub-application within FastAPI)
- **Authentication**: Session-based with signed cookies (SPEC req 31)
- **CSRF protection**: Token-based middleware (SPEC req 31)
- **Pages**: Member management, household settings, WAHA session setup

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
| LLM approach | LiteLLM + OpenRouter | Direct provider SDKs, Ollama | Provider-agnostic with unified tool calling, easy model switching, built-in retry/fallback |
| Database layer | SQLModel + Alembic | SQLAlchemy, Tortoise, Peewee, raw SQL | Pydantic + SQLAlchemy in one model class, native FastAPI fit, minimal boilerplate |
| Task scheduling | APScheduler v4 | Celery, arq, Huey, manual asyncio | Native async cron triggers, zero external deps, single-process compatible |
| Admin interface | FastHTML | SQLAdmin, Starlette Admin, React SPA | Pure Python (no JS/templates), full control over custom pages like WAHA session setup |
| Async processing | SQLite-backed job queue | BackgroundTasks, Redis+arq, asyncio.Queue | Durable (survives restarts), native dedup via PK, retry/backoff via run_after column, no external deps |
| HTTP client | httpx | aiohttp, requests | Async-native, clean API, widely adopted, pairs well with FastAPI |
| Rate limiting | aiolimiter | Manual token bucket, Redis-based | Lightweight async leaky-bucket, zero external deps |
