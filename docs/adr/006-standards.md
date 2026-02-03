# ADR 006: Repository Standards & Engineering Practices

**Status:** Accepted  
**Date:** 2026-01-14

## Context

To maintain code quality and velocity as a single developer, we need strict but automated standards. We want to avoid "bikeshedding" over formatting and ensure the codebase remains navigable as the AI logic grows.

## Decision

### 1. Repository Structure

We will adopt a **Functional Service-Layered Architecture**.

```text
src/
├── agents/         # Pydantic AI Agents, Tools, and Prompts
├── interface/      # FastAPI Routers (Webhooks, Admin) & WhatsApp Adapters
├── core/           # Config, Logging, Schema Management, DB Client
├── domain/         # Pydantic Data Models / DTOs
├── services/       # Functional Business Logic (Ledger, Bouncer, etc.)
└── main.py         # App Entrypoint
```text

### 2. Code Style & Linting

We strictly use the **Astral Stack** (`ruff`, `uv`, `ty`).

- **Package Manager:** `uv`.
- **Formatter:** `ruff format` (120 character line length).
- **Linter:** `ruff check` (Grouped imports, trailing commas).
- **Type Checking:** `ty` (Astral's high-performance type checker).
  - **Note:** Strict typing is mandatory for all arguments and return values.

### 3. Coding Principles

- **Minimalist Documentation:** Single-line descriptions only.
- **Functional over Class-based:** Use standalone functions unless state management strictly requires a class.
- **Guard Clauses:** Keep the "happy path" on the left margin.
- **Keyword-Only Arguments:** Required for functions with > 2 parameters.
- **No TODOs:** Do not commit `TODO` comments.

### 4. Git Workflow

- **Commits:** Conventional Commits specification preferred.

## Consequences

### Positive

- **Performance:** The Astral stack is significantly faster than legacy tools.
- **Readability:** Forcing "unnested" code and strict DTOs makes logic easy to follow.

### Negative

- **Tool Maturity:** `ty` is relatively new. We accept the risk for the benefit of speed and ecosystem consistency.

## Related ADRs

- [ADR 001: Technology Stack](001-stack.md) - Core technology choices
- [ADR 015: Type Safety](015-type-safety.md) - Detailed type checking approach
