# ADR 006: Repository Standards & Engineering Practices

## Status
Accepted

## Date
2026-01-14

## Context
To maintain code quality and velocity as a single developer (or small team), we need strict but automated standards. We want to avoid "bikeshedding" over formatting and ensure the codebase remains navigable as the AI logic grows.

## Decision

### 1. Repository Structure
We will adopt a **Service-Layered Architecture** within a monorepo-style folder structure.

```text
.
├── app/
│   ├── agents/         # Pydantic AI Agents & Prompts
│   ├── api/            # FastAPI Routers (Webhooks, Admin)
│   ├── core/           # Config, Logging, Security
│   ├── models/         # Pydantic Data Models (Shared)
│   ├── services/       # Business Logic (Auditor, Jury, Ledger)
│   └── main.py         # App Entrypoint
├── tests/              # Pytest Suite
├── scripts/            # Dev scripts (seed db, run checks)
├── docs/               # ADRs and Architecture notes
├── pyproject.toml      # Dependencies & Tool Config
└── .env.example        # Environment Template
```

### 2. Code Style & Linting
We will use the **Astral Stack** (`ruff`, `uv`, `ty`) for a high-performance developer experience.

*   **Package Manager:** `uv` (Fast replacement for pip/poetry).
*   **Formatter:** `ruff format` (Drop-in replacement for Black).
*   **Linter:** `ruff check` (Drop-in replacement for Flake8/Isort).
*   **Type Checking:** `ty` (Astral's high-performance type checker).
    *   *Note:* We enforce strict typing to catch agent-logic bugs at build time.

### 3. Coding Principles
*   **Minimal Comments:** Code should be self-documenting. Only comment *why* complex logic exists, never *what* the code is doing.
*   **Flat is Better Than Nested:** Avoid deep indentation. Use "Guard Clauses" (early returns) to keep the "happy path" on the left margin.
*   **DRY (Don't Repeat Yourself):** Abstract repeated logic into utility functions, especially for database queries and API calls.
*   **Strong Typing:** All functions must have type hints.

### 4. Git Workflow
*   **Branching:** Feature Branch Workflow (`feat/add-chore-tool`, `fix/verifier-bug`).
*   **Commits:** Conventional Commits specification.
    *   `feat: ...` for new capabilities.
    *   `fix: ...` for bug fixes.
    *   `docs: ...` for documentation.
    *   `refactor: ...` for code restructuring without behavior change.

## Consequences

### Positive
*   **Zero Ambiguity:** The linter dictates the style.
*   **Performance:** The Astral stack (`uv`, `ruff`, `ty`) is significantly faster than the legacy Python toolchain.
*   **Readability:** Forcing "unnested" code makes the logic easier to follow for both humans and LLMs.

### Negative
*   **Tool Maturity:** `ty` is newer than `mypy`. We accept the risk of potential instability for the benefit of speed.
