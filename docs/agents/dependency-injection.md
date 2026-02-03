# Dependency Injection

This page describes dependency injection patterns for Pydantic AI agents.

## Context

Never use global state. Use Pydantic AI's `RunContext[Deps]` to inject the Database Connection, User ID, and Current Time.

## Definition

Define a `Deps` dataclass in `src/agents/base.py`.
