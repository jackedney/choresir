# System Architecture

This page describes the overall system architecture of WhatsApp Home Boss.

## Overview

WhatsApp Home Boss is a household operating system that lives within WhatsApp. It uses
a "clean architecture" approach with clear separation of concerns:

- **Interface Layer**: FastAPI routes that receive webhooks from WhatsApp
- **Agent Layer**: Pydantic AI agents that interpret natural language commands
- **Service Layer**: Functional business logic that manages domain operations
- **Domain Layer**: Data transfer objects and business entities
- **Infrastructure Layer**: Database, logging, configuration, and scheduling

## Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         External Systems                              │
│  ┌─────────────┐              ┌─────────────┐                      │
│  │   WhatsApp  │              │  OpenRouter  │                      │
│  │   (WAHA)    │              │   (LLM API)  │                      │
│  └──────┬──────┘              └──────┬──────┘                      │
│         │                             │                              │
└─────────┼─────────────────────────────┼──────────────────────────────┘
          │                             │
          │ Webhook                     │ API Requests
          ▼                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Interface Layer                              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  FastAPI Router (webhook.py)                                   │  │
│  │  - Parse webhook payload                                        │  │
│  │  - Security validation (timestamp, nonce, rate limit)            │  │
│  │  - Route to background tasks                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  WhatsApp Adapters (whatsapp_parser.py, whatsapp_sender.py)      │  │
│  │  - Parse message format                                         │  │
│  │  - Send responses to WhatsApp                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                │ Background Task
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Agent Layer                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Pydantic AI Agent (choresir_agent.py)                         │  │
│  │  - Build user context (Deps)                                    │  │
│  │  - Call agent with LLM                                          │  │
│  │  - Execute tools based on LLM decisions                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Tools (tools/*.py)                                            │  │
│  │  - onboarding_tools.py (join requests)                          │  │
│  │  - chore_tools.py (manage chores)                               │  │
│  │  - verification_tools.py (verify completions)                    │  │
│  │  - pantry_tools.py (inventory management)                       │  │
│  │  - analytics_tools.py (stats and reports)                       │  │
│  │  - personal_chore_tools.py (private tasks)                      │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                │ Tool Execution
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Service Layer                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │
│  │ chore_service.py │  │ user_service.py  │  │ pantry_service.py     │ │
│  │ - CRUD operations│  │ - User mgmt     │  │ - Inventory tracking  │ │
│  │ - State machine │  │ - Join requests  │  │ - Shopping list       │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘ │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │
│  │verification_     │  │session_service.  │  │ analytics_service.   │ │
│  │service.py        │  │py               │  │py                    │ │
│  │ - Verify claims │  │ - Join flow     │  │ - Stats & reports    │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                │ Data Access
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Infrastructure Layer                             │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Database Client (db_client.py)                                 │  │
│  │  - Connection pooling with health checks                         │  │
│  │  - Automatic reconnection                                       │  │
│  │  - CRUD functions (create_record, get_record, etc.)             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │
│  │ PocketBase DB    │  │ Scheduler        │  │ Redis (Optional)      │ │
│  │ - users          │  │ - Cron jobs     │  │ - Rate limiting       │ │
│  │ - chores         │  │ - Reminders     │  │ - Caching            │ │
│  │ - logs           │  │ - Reports       │  │                      │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Message Processing Flow

1. **WhatsApp → WAHA**: User sends message to WhatsApp number
2. **WAHA → FastAPI**: Webhook POST request to `/webhook`
3. **FastAPI Validation**: Security checks (timestamp, nonce, rate limit)
4. **Immediate Response**: Return `200 OK` immediately
5. **Background Task**: Dispatch to `process_webhook_message()`
6. **Parse Message**: Extract text, phone number, message ID
7. **Duplicate Check**: Query `processed_messages` collection
8. **User Lookup**: Fetch user record from `users` collection
9. **Agent Execution**: Build `Deps` and run Pydantic AI agent
10. **Tool Calls**: Agent executes tools (chore tools, verification tools, etc.)
11. **Service Operations**: Tools call service functions for business logic
12. **Database Operations**: Services use `db_client` functions for CRUD
13. **Response**: Send WhatsApp message back to user
14. **Log Status**: Update `processed_messages` with success/error

### Key Design Decisions

**Why return `200 OK` immediately?**

- WhatsApp webhooks require quick responses (< 30s)
- AI processing can take 5-30+ seconds
- Background tasks prevent webhook timeouts
- Idempotency via `processed_messages` prevents double-processing

**Why functional services instead of classes?**

- Simpler testing (pure functions are easy to mock)
- Easier to reason about (no hidden state)
- Fits Python's functional programming style
- No need for dependency injection frameworks

**Why Pydantic AI agents?**

- Type-safe tool definitions (Pydantic models)
- Automatic LLM schema generation
- Built-in retry logic
- Structured dependency injection via `RunContext[Deps]`
