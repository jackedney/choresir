# Code Quality

This guide covers code quality standards and tools for WhatsApp Home Boss.

## Tools

We use the **Astral Stack** for code quality:

- **Package Manager:** `uv` (Use for all dependency management)
- **Linter/Formatter:** `ruff` (Replacement for Black/Isort/Flake8)
- **Type Checker:** `ty` (Astral's high-performance type checker)

## Code Quality Commands

Before committing code, run these checks in order:

```bash
# 1. Format code with ruff
uv run ruff format .

# 2. Lint code with ruff and auto-fix
uv run ruff check . --fix

# 3. Type check with ty
uv run ty check src

# 4. Run tests
uv run pytest
```

## Pre-Commit Checklist

Before committing your changes, verify:

- [ ] Code is formatted (`uv run ruff format .`)
- [ ] No linting errors (`uv run ruff check .`)
- [ ] Type checking passes (`uv run ty check src`)
- [ ] All tests pass (`uv run pytest`)
- [ ] No uncommitted changes remain

## Quality Gates

### What Happens If You Skip Quality Gates?

Skipping quality gates causes CI/CD failures and prevents your changes from being merged. Here are common scenarios:

#### Scenario 1: Skipping type checking

```bash
# BAD: Skipping ty check
git commit -m "feat: new feature"
# CI fails with: "Type checking errors found in 5 files"
# Your PR cannot be merged until fixed
```

#### Scenario 2: Skipping formatting

```bash
# BAD: Unformatted code
git commit -m "feat: new feature"
# CI fails with: "Code not formatted according to ruff"
# Must run `ruff format .` and commit again
```

#### Scenario 3: Skipping tests

```bash
# BAD: Tests not passing
git commit -m "feat: new feature"
# CI fails with: "3 tests failed"
# Must fix failing tests before merge
```

### Required Checks

The following checks must pass before any code is merged:

1. **Formatting:** `ruff format` must have no issues
2. **Linting:** `ruff check` must return zero errors
3. **Type Checking:** `ty check src` must return zero errors
4. **Tests:** `pytest` must pass all tests

## Ruff Configuration

Ruff is configured in `pyproject.toml` with these settings:

### Formatting Rules

- **Line Length:** 120 characters
- **Quotes:** Double quotes (`"`) preferred
- **Indent Style:** Spaces
- **Trailing Commas:** Mandatory for multi-line lists/dictionaries

### Linting Rules

Ruff enforces Python best practices with these rule sets:

- **E, W:** pycodestyle (errors and warnings)
- **F:** pyflakes (undefined names, unused imports)
- **I:** isort (import sorting)
- **UP:** pyupgrade (modern Python syntax)
- **B:** flake8-bugbear (common bugs)
- **N:** pep8-naming (naming conventions)
- **ANN:** flake8-annotations (type annotations)
- **ASYNC:** flake8-async (async best practices)
- **S:** flake8-bandit (security issues)
- **COM:** flake8-commas (trailing commas)
- **T20:** flake8-print (print statements in production)
- **RET:** flake8-return (return statement issues)
- **SIM:** flake8-simplify (code simplification)
- **ARG:** flake8-unused-arguments (unused function arguments)
- **PTH:** flake8-use-pathlib (pathlib over os.path)
- **ERA:** eradicate (commented-out code)
- **PL:** pylint (general code quality)
- **RUF:** ruff-specific rules

## Type Checking with ty

### Why ty?

Astral's `ty` is 10-60x faster than mypy/pyright, with better error messages and first-class support for modern Python features.

### Running ty

```bash
# Check entire src directory
uv run ty check src

# Check specific file
uv run ty check src/agents/choresir_agent.py

# Watch mode (re-check on file changes)
uv run ty check src --watch

# Verbose mode with explanations
uv run ty check src --explain
```

### Type Checking Requirements

All code must have strict type hints:

- Function arguments must be typed
- Return values must be typed (including `-> None`)
- Async functions must have proper return types
- Pydantic models for all data structures

### Common Type Issues

**Missing return type annotation:**

```python
# BAD
def get_user(user_id: str):
    pass

# GOOD
def get_user(user_id: str) -> User:
    pass
```

**Untyped function parameters:**

```python
# BAD
def process(data):
    pass

# GOOD
def process(data: dict[str, Any]) -> None:
    pass
```

**Missing -> None:**

```python
# BAD
def log_message(message: str):
    logger.info(message)

# GOOD
def log_message(message: str) -> None:
    logger.info(message)
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_agents.py

# Run specific test
uv run pytest tests/test_agents.py::test_create_chore

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

### Test Organization

```text
tests/
├── test_agents.py      # Agent tests
├── test_services.py    # Service tests
├── test_interface.py   # API endpoint tests
└── conftest.py         # Shared fixtures
```

### Test Fixtures

The project uses pytest fixtures for setup:

- `client`: FastAPI test client
- `db`: Ephemeral PocketBase instance
- `deps`: Dependency injection context

### Integration Tests

Tests run against real PocketBase instances (not mocked). Tests use temporary databases that are cleaned
up after each test run.

## Import Organization

Imports must be grouped by type:

```python
# 1. Standard Library
import logging
from typing import Any

# 2. Third Party
from fastapi import FastAPI
from pydantic import BaseModel

# 3. Local
from src.domain.models import Chore
from src.services.database import DatabaseService
```

## Security Checks

Ruff includes flake8-bandit (rule set **S**) for security checks:

- Hardcoded passwords and tokens (S105, S106)
- Subprocess calls (S603)
- Debug print statements (T201)
- Other security vulnerabilities

Security issues in tests are allowed with per-file exceptions.

## Documentation Quality

For documentation files, run these checks:

```bash
# Check Markdown formatting
npx markdownlint docs/

# Check writing style and terminology
npx textlint docs/
```

Or use npm scripts:

```bash
# Check Markdown formatting
npm run lint:md

# Check writing style and terminology
npm run lint:text

# Run both checks
npm run lint:docs
```

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
