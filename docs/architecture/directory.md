# Directory Structure

This page describes the directory structure and purpose of each directory.

## Layout

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

## Directory Purposes

### agents/

Contains Pydantic AI agent implementations with logic, tools, and prompts.

### core/

Contains core application components:

- Configuration
- Logging
- Schema definitions
- Database client

### domain/

Contains Pydantic DTOs and domain entities.

### interface/

Contains FastAPI routers and WhatsApp adapters.

### services/

Contains functional business logic. Use standalone functions in modules rather
than service classes, unless state management requires a class.

### main.py

Application entrypoint.
