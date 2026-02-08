# Instructions for AI Coding Assistants

**Target Audience:** AI Agents (Claude, Gemini, etc.) modifying this codebase.
**Purpose:** This document serves as the "System Prompt" extension for this repository.
It provides a quick reference to the coding standards, architectural patterns, and
operational constraints you must follow.

**CRITICAL:** This file is NOT for defining the business logic of agents *within*
the application (e.g., `choresir`). Those specifications belong in
`docs/decisions/` (e.g., `docs/decisions/002-agents.md`).

---

## Documentation

This repository uses MkDocs for comprehensive documentation. Full documentation is available in the `docs/` directory.

**Quick Reference:**

- **Project Context:** [docs/contributors/context.md](docs/contributors/context.md)
- **Development Workflow:** [docs/contributors/development.md](docs/contributors/development.md)
- **Toolchain & Style:** [docs/contributors/toolchain.md](docs/contributors/toolchain.md)
- **Code Quality:** [docs/contributors/code-quality.md](docs/contributors/code-quality.md)
- **Logging & Observability:** [docs/contributors/logging.md](docs/contributors/logging.md)
- **Architecture:** [docs/architecture/](docs/architecture/index.md)
- **Agent Development:** [docs/agents/](docs/agents/index.md)
- **ADRs:** [docs/adr/](docs/adr/index.md)

## Building Documentation

To build and view documentation locally:

```bash
# Serve documentation locally (live reload)
mkdocs serve

# Build static documentation
mkdocs build
```

Then visit `http://127.0.0.1:8000`

## Quick Start: Code Quality Commands

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

## Key Standards (Summary)

### Project Stack

- **Runtime:** Python 3.12+
- **Framework:** FastAPI
- **Database:** SQLite (local embedded via `aiosqlite`)
- **Agent Framework:** Pydantic AI
- **Philosophy:** Maintainability over scalability

### Toolchain (Astral Stack)

- **Package Manager:** `uv`
- **Linter/Formatter:** `ruff`
- **Type Checker:** `ty`

### Core Conventions

- **Line Length:** 120 characters
- **Quotes:** Double quotes (`"`)
- **Trailing Commas:** Mandatory for multi-line lists/dictionaries
- **Functional Preference:** Use standalone functions, not service classes
- **Keyword-Only Arguments:** Enforce `*` for functions with > 2 parameters
- **DTOs Only:** Use Pydantic models, not raw dicts
- **No Custom Exceptions:** Use standard Python exceptions or `FastAPI.HTTPException`
- **No TODOs:** Do not commit TODO comments
- **Documentation:** Minimalist single-line descriptions
- **Typing:** Strict type hints required for ALL arguments and return values (including `-> None`)

### Directory Structure

All logic must reside in `src/`:

```text
src/
├── agents/         # Pydantic AI Agents (Logic, Tools, Prompts)
├── core/           # Configuration, Logging, Schema, DB Client
├── domain/         # Pydantic DTOs / Entities
├── interface/      # FastAPI Routers & WhatsApp Adapters
├── services/       # Functional Business Logic
└── main.py         # Application Entrypoint
```

### Agent Development

- **Naming:** Snake case for agents/tools, PascalCase for models
- **Dependency Injection:** Use `RunContext[Deps]` (no global state)
- **Tools:** Single Pydantic Model argument, return error strings (not exceptions)

### Database Interaction

- **Access:** Use `src/core/db_client` wrapper functions
- **Encapsulation:** Never access SQLite directly outside of `db_client`
- **Schema:** Code-first approach via `src/core/schema.py`

### Async & Concurrency

- **Async First:** Use `async def` for all routes and services
- **Background Tasks:** Webhooks return `200 OK` immediately, use `FastAPI.BackgroundTasks`

### Logging

- **Library:** Use Python's standard `logging` module
- **Pattern:** `import logging; logger = logging.getLogger(__name__)`
- **Logfire:** Automatically captures standard logging (don't use direct `logfire` calls)
- **Structured:** Use `extra` parameter for context fields
- **Levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL

### Testing

- **Integration:** Use `pytest`. Tests run against a temporary SQLite database.
- **No Mocks:** Prefer testing against the temporary database over mocking DB calls.

## Pre-Commit Checklist

Before committing your changes, verify:

- [ ] Code is formatted (`uv run ruff format .`)
- [ ] No linting errors (`uv run ruff check .`)
- [ ] Type checking passes (`uv run ty check src`)
- [ ] All tests pass (`uv run pytest`)
- [ ] No uncommitted changes remain
- [ ] No TODO comments in code
- [ ] All functions have type hints
- [ ] Documentation checks pass (`npm run lint:docs` if docs were changed)

## Documentation Quality Checks

For documentation files, run these checks:

```bash
# Check Markdown formatting
npm run lint:md

# Check writing style and terminology
npm run lint:text

# Run both checks
npm run lint:docs
```

Both markdownlint and textlint are installed via npm and configured for this project.

Alternative: You can also use `uv run markdownlint docs/` for markdownlint checks. Textlint should be run via npm scripts.

### What the checks validate

**markdownlint** validates Markdown formatting:

- Line length (120 characters)
- Proper list spacing and indentation
- Code block formatting
- Heading spacing

**textlint** validates writing quality:

- **write-good rule**: Passive voice, wordiness, weak words
- **terminology rule**: Correct terminology (e.g., "function parameter" not "function argument", "Git" not "git")

These checks must pass before documentation changes can be merged.

## Further Reading

- [Contributors Guide](docs/contributors/index.md) - Comprehensive contributor documentation
- [Architecture Guide](docs/architecture/index.md) - System design and patterns
- [Agent Implementation Guide](docs/agents/index.md) - Building Pydantic AI agents
- [ADR-017](docs/adr/017-type-safety.md) - Type checking configuration details
