# ADR 002: Use of Pydantic AI for Agentic Logic

## Status
Accepted

## Date
2026-01-14

## Context
The application requires an LLM to interpret natural language, extract structured entities (Chore, Time, Assignee), and execute database tools. The landscape includes LangChain, AutoGen, and n8n. The primary constraint is maintainability for a single developer.

## Decision
We will use **Pydantic AI**.

1.  We rejected **LangChain** due to its high abstraction complexity and frequent breaking changes.
2.  We rejected **n8n** because the complex business logic (voting/swapping) is harder to version control and debug in a visual flowchart.
3.  **Pydantic AI** integrates natively with FastAPI (both use Pydantic models), allowing us to share data validation schemas between the HTTP API and the AI Agent.

## Consequences

### Positive
*   Type safety.
*   Pure Python code (easier to debug).
*   Lightweight dependency.

### Negative
*   Smaller ecosystem/community support compared to LangChain.

### Mitigation
We will rely on raw OpenAI-compatible API calls if Pydantic AI lacks a specific specific integration we need.
