# Engineering Patterns

This page describes the engineering patterns used in WhatsApp Home Boss.

## Functional Preference

Use standalone functions in modules (`src/services/ledger.py`) rather than
Service Classes, unless state management requires a class.

## Keyword-Only Arguments

Enforce `*` for functions with > 2 parameters:

```python
def create_task(*, name, due, user):
    ...
```

## DTOs Only

Strictly use Pydantic models for passing data between layers. No raw dicts.

## No Custom Exceptions

Use standard Python exceptions or `FastAPI.HTTPException`.

## No TODOs

Do not commit `TODO` comments.

## Documentation

Minimalist single-line descriptions. No verbose Google-style docstrings.

## Typing

Strict type hints required for ALL arguments and return values (including `-> None`).
