# Code Quality

This guide covers code quality standards and tools for WhatsApp Home Boss.

## Tools

We use the **Astral Stack** for code quality:

- **Package Manager:** `uv` (Use for all dependency management)
- **Linter/Formatter:** `ruff` (Replacement for Black/Isort/Flake8)
- **Type Checker:** `ty` (Astral's high-performance type checker)

## Commands

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

## Pre-Commit Checklist

- [ ] Code is formatted (`ruff format .`)
- [ ] No linting errors (`ruff check .`)
- [ ] Type checking passes (`ty check src`)
- [ ] All tests pass (`pytest`)
- [ ] No uncommitted changes
