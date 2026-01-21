# Instructions for AI Coding Assistants

**Target Audience:** AI Agents (Claude, Gemini, etc.) modifying this codebase.
**Purpose:** This document serves as the "System Prompt" extension for this repository. It defines the coding standards, architectural patterns, and operational constraints you must follow.

**CRITICAL:** This file is NOT for defining the business logic of agents *within* the application (e.g., `choresir`). Those specifications belong in `docs/decisions/` (e.g., `docs/decisions/002-agents.md`).

---

## 1. Project Context
*   **Name:** Whatsapp Home Boss
*   **Stack:** The "Indie Stack"
    *   **Runtime:** Python 3.12+
    *   **Framework:** FastAPI
    *   **Database:** PocketBase (SQLite mode)
    *   **Agent Framework:** Pydantic AI
*   **Philosophy:** Maintainability over scalability. Single-developer friendly.

## 2. Toolchain & Style (The Astral Stack)
We strictly enforce the **Astral** toolchain standards.

### A. Core Tools
*   **Package Manager:** `uv` (Use for all dependency management).
*   **Linter/Formatter:** `ruff` (Replacement for Black/Isort/Flake8).
*   **Type Checker:** `ty` (Astral's high-performance type checker).

### B. Formatting Rules
*   **Line Length:** 120 characters.
*   **Quotes:** Double quotes (`"`) preferred.
*   **Trailing Commas:** Mandatory for multi-line lists/dictionaries.
*   **Imports:** Grouped by type (Standard Lib, Third Party, Local).

### C. Coding Conventions
*   **Functional Preference:** Use standalone functions in modules (`src/services/ledger.py`) rather than Service Classes, unless state management requires a class.
*   **Keyword-Only Arguments:** Enforce `*` for functions with > 2 parameters (e.g., `def create_task(*, name, due, user):`).
*   **DTOs Only:** Strictly use Pydantic models for passing data between layers. No raw dicts.
*   **No Custom Exceptions:** Use standard Python exceptions or `FastAPI.HTTPException`.
*   **No TODOs:** Do not commit `TODO` comments.
*   **Documentation:** Minimalist single-line descriptions. No verbose Google-style docstrings.
*   **Typing:** Strict type hints required for ALL arguments and return values (including `-> None`).

## 3. Architecture & Directory Structure
All logic must reside in `src/`.
```text
src/
├── agents/         # Pydantic AI Agents (Logic, Tools, Prompts)
├── core/           # Configuration, Logging, Schema, DB Client
├── domain/         # Pydantic DTOs / Entities
├── interface/      # FastAPI Routers & WhatsApp Adapters
├── services/       # Functional Business Logic (e.g., ledger.py)
└── main.py         # Application Entrypoint
```

## 4. Engineering Patterns

### A. Database Interaction (PocketBase)
*   **Access:** Use the official `pocketbase` Python SDK.
*   **Encapsulation:** Never import the PocketBase client directly into Routers or Agents. Always use `src.services.database.DatabaseService`.
*   **Schema:** "Code-First" approach. `src/core/schema.py` syncs the DB structure on startup.

### B. Async & Concurrency
*   **Async First:** Use `async def` for all routes and services.
*   **Background Tasks:** WhatsApp Webhooks MUST return `200 OK` immediately. Use `FastAPI.BackgroundTasks` for AI processing.

### C. Security & Robustness
*   **Signature:** Validate `X-Hub-Signature-256` on all webhooks.
*   **Idempotency:** check `processed_message_ids` to prevent double-replies.
*   **Cost Cap:** Hard limit of ~$0.10/day (track usage in memory/DB).

## 5. Agent Development Standards
Specific rules for building Pydantic AI agents in `src/agents/`.

### A. Naming Conventions
*   **Agents:** Snake case (e.g., `household_manager`).
*   **Tools:** Snake case, prefixed with `tool_` (e.g., `tool_log_chore`).
*   **Models:** PascalCase Pydantic models (e.g., `LogChoreParams`).

### B. Dependency Injection
*   **Context:** Never use global state. Use Pydantic AI's `RunContext[Deps]` to inject the Database Connection, User ID, and Current Time.
*   **Definition:** define a `Deps` dataclass in `src/agents/base.py`.

### C. Tool Design
*   **Explicit Arguments:** All tools must take a single Pydantic Model as an argument (or named args typed with Pydantic primitives) to ensure schema generation works perfectly with the LLM.
*   **Error Handling:** Tools must return descriptive error strings (e.g., "Error: Chore not found") rather than raising exceptions.

## 6. Logging & Observability

### A. Standard Logging Pattern
*   **Library:** Use Python's standard `logging` module in all files.
*   **Pattern:** Always include at module level:
    ```python
    import logging
    logger = logging.getLogger(__name__)
    ```
*   **Logfire Integration:** Logfire automatically captures all standard logging calls via `logfire.instrument_logging()` configured in `src/core/logging.py`.

### B. Structured Logging
*   **Context Fields:** Use `extra` parameter for structured data:
    ```python
    logger.info("User action", extra={"user_id": "123", "action": "claim_chore"})
    ```
*   **Utilities:** Use helpers from `src/core/logging.py` for common patterns:
    ```python
    from src.core.logging import log_with_user_context
    log_with_user_context(logger, "info", "Action performed", user_id="123", action="claim")
    ```

### C. Log Levels
*   **DEBUG:** Fine-grained diagnostic info (cache hits, internal state)
*   **INFO:** General operational events (user actions, job execution)
*   **WARNING:** Recoverable issues (failed retries, degraded performance)
*   **ERROR:** Failures requiring attention (DB errors, API failures)
*   **CRITICAL:** System-threatening failures (startup failures, data corruption)

### D. Best Practices
*   **Never use direct logfire calls:** Use standard logging instead of `logfire.info()`, `logfire.error()`, etc.
*   **Consistent context:** Include relevant context fields (user_id, request_id, operation_type) for filtering and debugging.
*   **No sensitive data:** Never log passwords, tokens, or personal information.
*   **Actionable messages:** Log messages should be clear and actionable.

## 7. Testing Strategy
*   **Integration:** Use `pytest` with an ephemeral PocketBase instance (via `TestClient` fixture).
*   **No Mocks:** Do not mock the database logic. Test against the real (temporary) binary.

## 8. Development Workflow

### A. Code Quality Commands

Before committing code, run these checks:

```bash
# Format code with ruff
uv run ruff format .

# Lint code with ruff
uv run ruff check . --fix

# Type check with ty
uv run ty check src

# Run tests
uv run pytest
```

### B. Pre-Commit Checklist

- [ ] Code is formatted (`ruff format .`)
- [ ] No linting errors (`ruff check .`)
- [ ] Type checking passes (`ty check src`)
- [ ] All tests pass (`pytest`)
- [ ] No uncommitted changes

### C. Type Checking with ty

**Why ty?** Astral's `ty` is 10-60x faster than mypy/pyright, with better error messages and first-class support for modern Python features.

**Running ty:**
```bash
# Check entire src directory
uv run ty check src

# Check specific file
uv run ty check src/agents/choresir_agent.py

# Watch mode (re-check on file changes)
uv run ty check src --watch
```

**Common Type Issues:**
- Missing return type annotations
- Untyped function parameters
- Incorrect type hints for async functions
- Missing `-> None` for functions without return values

See [ADR-017](docs/decisions/017-type-safety.md) for more details on type checking configuration.
