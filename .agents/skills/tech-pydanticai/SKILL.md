---
name: tech-pydanticai
description: Reference guide for PydanticAI — AI agent framework with typed tools, structured output, and dynamic prompts
user-invocable: false
---

# PydanticAI

> Purpose: AI agent framework — tool calling, structured output validation, dynamic system prompts
> Docs: https://ai.pydantic.dev
> Version researched: latest

## Quick Start

```python
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass

@dataclass
class AgentDeps:
    session: AsyncSession
    sender: MessageSender

agent = Agent(
    "openai/gpt-4o",  # or via LiteLLM: "litellm/openrouter/anthropic/claude-opus-4"
    deps_type=AgentDeps,
    system_prompt="You are a household task assistant.",
)
```

## Common Patterns

### Static + dynamic system prompts

```python
agent = Agent(
    "openai/gpt-4o",
    deps_type=AgentDeps,
    system_prompt="You are a helpful household assistant.",  # static, version-controlled
)

@agent.system_prompt
async def add_household_context(ctx: RunContext[AgentDeps]) -> str:
    members = await get_members(ctx.deps.session)
    tasks = await get_active_tasks(ctx.deps.session)
    return f"Members: {members}\nActive tasks: {tasks}"
```

### Defining tools with typed parameters

```python
@agent.tool
async def create_task(
    ctx: RunContext[AgentDeps],
    title: str,
    assignee_id: int,
    deadline: str | None = None,
) -> str:
    """Create a new household task."""
    try:
        task = await task_service.create(ctx.deps.session, title, assignee_id, deadline)
        return f"Task '{task.title}' created and assigned."
    except NotFoundError:
        return "Member not found."
```

### Running the agent

```python
result = await agent.run(
    user_message,
    deps=AgentDeps(session=session, sender=sender),
)
response_text = result.output  # str (or typed Pydantic model if output_type set)
```

### Structured output (Pydantic model)

```python
from pydantic import BaseModel

class TaskSummary(BaseModel):
    task_count: int
    overdue_count: int
    top_member: str

summary_agent = Agent(
    "openai/gpt-4o",
    output_type=TaskSummary,
)
result = await summary_agent.run("Summarize household tasks")
summary = result.output  # typed TaskSummary instance
```

### LiteLLM/OpenRouter integration

```python
# Model string format for LiteLLM provider:
# "litellm/<provider>/<model>"
agent = Agent("litellm/openrouter/anthropic/claude-opus-4-5")

# Or set via environment / settings
import os
os.environ["OPENROUTER_API_KEY"] = "..."
```

## Gotchas & Pitfalls

- **Tools must not raise exceptions**: A tool that raises kills the agent run. Always catch domain errors and return descriptive strings.
- **`deps_type` must match `RunContext[T]` type**: If `deps_type=AgentDeps`, every tool using `ctx: RunContext[...]` must use `RunContext[AgentDeps]`.
- **`ctx.deps` is injected at `agent.run()` time**: Don't try to access DB or external resources without deps — they're not available at agent definition time.
- **System prompt functions can be async**: Both sync and async functions work with `@agent.system_prompt`.
- **`retries` parameter**: Controls auto-retry on malformed structured output (default 1). Increase for flaky models.
- **Tool docstrings become schema descriptions**: Write clear docstrings — the LLM uses them to decide when to call each tool.

## Idiomatic Usage

Group tools into domain modules and use a registry pattern to keep the agent definition clean:

```python
# agent/registry.py
registry = ToolRegistry()

# agent/tools/tasks.py
@registry.register
async def create_task(ctx: RunContext[AgentDeps], ...) -> str: ...

# agent/agent.py
registry.apply(agent)  # registers all tools at once
```

Prefer returning plain strings from tools — the LLM integrates them naturally into its response. Return structured data only when the agent needs to process it further.
