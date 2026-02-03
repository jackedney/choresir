# Tool Design

This page describes tool design patterns for Pydantic AI agents.

## Tool Signature

All tools must follow this signature pattern:

```python
async def tool_name(ctx: RunContext[Deps], params: SomeModel) -> str:
    """Tool description for LLM."""
    try:
        # Tool implementation
        return "Success message"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.error("Unexpected error", extra={"error": str(e)})
        return "Error: Unable to complete operation"
```

## Explicit Arguments

All tools must take a single Pydantic Model as the second argument (or named args
typed with Pydantic primitives) to ensure schema generation works perfectly with
the LLM.

### Required Parameters

1. `ctx: RunContext[Deps]` - Runtime context with injected dependencies
2. `params: SomeModel` - Pydantic model with tool parameters

### Parameter Model Design

Define parameter models as Pydantic BaseModels with Field descriptions:

```python
from pydantic import BaseModel, Field

class LogChore(BaseModel):
    """Parameters for logging a chore completion."""

    chore_title_fuzzy: str = Field(description="Chore title or partial match (fuzzy search)")
    notes: str | None = Field(default=None, description="Optional notes about completion")
    is_swap: bool = Field(
        default=False,
        description="True if this is a Robin Hood swap (one user doing another's chore)",
    )
```

### Why This Pattern

- Pydantic models automatically generate JSON schemas for the LLM
- Field descriptions help the LLM understand parameter purposes
- Type annotations enable validation and type checking
- Default values make optional parameters clear

## Error Handling

Tools must return descriptive error strings (e.g., "Error: Chore not found")
rather than raising exceptions.

### Error Message Format

All error messages must start with `"Error: "` followed by a clear description:

```python
# Good - clear error message
return "Error: Chore not found matching 'dishes'"

# Bad - doesn't start with Error:
return "Chore not found"

# Bad - too vague
return "Error: Something went wrong"
```

### Exception Handling Pattern

Wrap tool logic in try-except blocks:

```python
async def tool_log_chore(ctx: RunContext[Deps], params: LogChore) -> str:
    """Log a chore completion and request verification."""
    try:
        # Tool implementation
        chore_id = await chore_service.log_completion(params.chore_title_fuzzy)
        return f"Logged chore {chore_id}"

    except ValueError as e:
        # Expected business logic errors
        logger.warning("Chore logging failed", extra={"error": str(e)})
        return f"Error: {e!s}"

    except Exception as e:
        # Unexpected errors - log and return generic message
        logger.error("Unexpected error in tool_log_chore", extra={"error": str(e)})
        return "Error: Unable to log chore. Please try again."
```

### Why Return Error Strings

- Exceptions crash the agent execution and provide poor UX
- Error strings are fed back to the LLM for context
- Users see clear, actionable error messages
- Logging captures technical details separately

## Example: tool_log_chore

Here's a complete example from `src/agents/tools/chore_tools.py`:

```python
"""Chore management tools for the choresir agent."""

import logging

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from src.agents.base import Deps
from src.services import chore_service, user_service


logger = logging.getLogger(__name__)


class LogChore(BaseModel):
    """Parameters for logging a chore completion."""

    chore_title_fuzzy: str = Field(description="Chore title or partial match (fuzzy search)")
    notes: str | None = Field(default=None, description="Optional notes about completion")
    is_swap: bool = Field(
        default=False,
        description="True if this is a Robin Hood swap (one user doing another's chore)",
    )


async def tool_log_chore(ctx: RunContext[Deps], params: LogChore) -> str:
    """
    Log a chore completion and request verification.

    Supports fuzzy matching for chore titles and Robin Hood swaps.

    Args:
        ctx: Agent runtime context with dependencies
        params: Chore logging parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_log_chore", title=params.chore_title_fuzzy):
            # Get all household chores to fuzzy match
            all_chores = await chore_service.get_chores()

            # Fuzzy match the chore by title
            household_match = _fuzzy_match_chore(all_chores, params.chore_title_fuzzy)

            # Validate chore exists
            if not household_match:
                return f"Error: No household chore found matching '{params.chore_title_fuzzy}'"

            chore_id = household_match["id"]
            chore_title = household_match["title"]

            # Log the completion
            await verification_service.request_verification(
                chore_id=chore_id,
                claimer_user_id=ctx.deps.user_id,
                notes=params.notes or "",
                is_swap=params.is_swap,
            )

            swap_msg = " (Robin Hood swap)" if params.is_swap else ""
            return (
                f"Logged completion of '{chore_title}'{swap_msg}. "
                "Awaiting verification from another household member."
            )

    except ValueError as e:
        logger.warning("Chore logging failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_log_chore", extra={"error": str(e)})
        return "Error: Unable to log chore. Please try again."
```

## Negative Case: Raising Exceptions

Incorrect pattern that should be avoided:

```python
# Bad - raising exceptions in tools
async def tool_bad_example(ctx: RunContext[Deps], params: SomeParams) -> str:
    """Bad pattern - raises exceptions."""
    if not params.id:
        raise ValueError("ID is required")  # Bad! Crashes agent

    # Tool logic...
    return "Success"
```

Correct pattern using error strings:

```python
# Good - returning error strings
async def tool_good_example(ctx: RunContext[Deps], params: SomeParams) -> str:
    """Good pattern - returns error strings."""
    if not params.id:
        return "Error: ID is required"  # Good! Agent can continue

    # Tool logic...
    return "Success"
```

## Logging in Tools

Use Python's standard `logging` module with Logfire spans:

```python
import logging
import logfire

logger = logging.getLogger(__name__)

async def tool_with_logging(ctx: RunContext[Deps], params: SomeParams) -> str:
    """Tool with logging."""
    try:
        with logfire.span("tool_name", param1=params.field1):
            logger.info("Tool started", extra={"user_id": ctx.deps.user_id})
            # Tool implementation
            logger.info("Tool completed", extra={"result": "success"})
            return "Success"
    except Exception as e:
        logger.error("Tool failed", extra={"error": str(e)})
        return "Error: Operation failed"
```

## Registering Tools

Tools are registered via the `register_tools` function in each tool module:

```python
from pydantic_ai import Agent
from src.agents.base import Deps

def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent."""
    agent.tool(tool_log_chore)
    agent.tool(tool_define_chore)
```

The agent instance calls this during initialization:

```python
# In agent_instance.py
from src.agents.tools import chore_tools

def _register_all_tools(agent_instance: Agent[Deps, str]) -> None:
    """Register all tool modules with the agent."""
    chore_tools.register_tools(agent_instance)
    # ... other tool modules
```
