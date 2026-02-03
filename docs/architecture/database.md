# Database Patterns

This page describes database interaction patterns in WhatsApp Home Boss.

## Access

Use the official `pocketbase` Python SDK.

## Encapsulation

Never import the PocketBase client directly into Routers or Agents. Always use `src.services.database.DatabaseService`.

## Schema

"Code-First" approach. `src/core/schema.py` syncs the DB structure on startup.
