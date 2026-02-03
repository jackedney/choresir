# Project Context

This page provides context about the WhatsApp Home Boss project.

## Project Overview

**Name:** WhatsApp Home Boss

**Description:** A household operating system that lives within WhatsApp, managing chores,
pantry inventory, and household analytics through natural language commands.

## Technology Stack: The "Indie Stack"

The project uses a carefully selected "indie stack" focused on maintainability and single-developer friendliness.

### Runtime

### Python 3.12+

- Modern Python features for type safety and readability
- Async/await for concurrent request handling
- Extensive package ecosystem

### Framework

### FastAPI

- Modern, fast (high-performance) web framework
- Automatic data validation with Pydantic
- Async/await support
- Built-in OpenAPI documentation
- Background task support for webhook processing

### Database

### PocketBase (SQLite mode)

- Self-hosted database (no cloud dependencies)
- Code-first schema management
- Real-time subscriptions (unused but available)
- Admin UI for debugging
- Simple deployment (single binary)

### Agent Framework

### Pydantic AI

- Type-safe agent and tool definitions
- Automatic LLM schema generation from Pydantic models
- Built-in retry logic
- Structured dependency injection via `RunContext[Deps]`

## Philosophy

### Maintainability over scalability

This project prioritizes code maintainability over extreme scalability:

- **Single-developer friendly:** Easy to understand and modify by one person
- **Clear architecture:** Separation of concerns with well-defined layers
- **Functional patterns:** Simple functions over complex classes
- **Type safety:** Comprehensive type hints with `ty` type checker
- **Automated quality:** Ruff formatter/linter, ty type checker, pytest

## External Integrations

### WhatsApp: WAHA

**WhatsApp HTTP API (WAHA)** provides the WhatsApp integration:

- Send and receive WhatsApp messages
- Webhook support for incoming messages
- Message templates for structured interactions

**Deployment:** Docker container (`devlikeapro/waha`)

### LLM API: OpenRouter

**OpenRouter** provides LLM API access:

- Support for multiple LLM providers (OpenAI, Anthropic, etc.)
- Consistent API across providers
- Cost transparency and tracking

**Usage:**

- Agent interpretation of natural language commands
- Decision-making for chore assignment and verification
- Intelligent responses to user queries

## Architecture Layers

The application follows a clean architecture approach:

1. **Interface Layer:** FastAPI routes and WhatsApp adapters
2. **Agent Layer:** Pydantic AI agents and tools
3. **Service Layer:** Functional business logic
4. **Domain Layer:** Pydantic DTOs and entities
5. **Infrastructure Layer:** Database, logging, configuration

See [System Architecture](../architecture/system.md) for details.

## Key Features

- **Household Chores:** Create, assign, track, and verify chores
- **Personal Chores:** Private task management with optional accountability
- **Pantry & Shopping:** Track inventory and generate shopping lists
- **Analytics:** Stats, leaderboards, and reports
- **Verification System:** Confirm chore completions
- **Natural Language:** Interact via conversational commands

## Development Goals

- **Code Quality:** Strict type checking, formatting, and linting standards
- **Testing:** Integration tests with real PocketBase instances
- **Documentation:** Comprehensive contributor and user guides
- **Simplicity:** Avoid over-engineering; prefer straightforward solutions
- **Robustness:** Idempotency, rate limiting, and error handling
