# Agents

## Naming

- Agents: `snake_case` (e.g., `choresir_agent`)
- Tools: `tool_` prefix (e.g., `tool_log_chore`)
- Parameter models: `PascalCase` (e.g., `LogChore`)

## Tool Template

```python
from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from src.agents.base import Deps
import logging
import logfire

logger = logging.getLogger(__name__)

class MyParams(BaseModel):
    """Parameter model with Field descriptions for LLM."""
    name: str = Field(description="Item name")
    optional_field: str | None = Field(default=None, description="Optional")

async def tool_my_action(ctx: RunContext[Deps], params: MyParams) -> str:
    """Single-line description for LLM."""
    try:
        with logfire.span("tool_my_action", name=params.name):
            # Use ctx.deps for db, user_id, user_name, etc.
            result = await some_service.do_thing(
                name=params.name,
                user_id=ctx.deps.user_id,
            )
            return f"Success: {result}"
    except ValueError as e:
        logger.warning("Expected error", extra={"error": str(e)})
        return f"Error: {e}"
    except Exception as e:
        logger.error("Unexpected error", extra={"error": str(e)})
        return "Error: Unable to complete. Please try again."
```

## Key Rules

1. **Return error strings, don't raise exceptions** - Errors go back to LLM for context
2. **All errors start with "Error: "** - Consistent format
3. **Use `ctx.deps`** - Never global state
4. **Log with logfire spans** - Observability
5. **Field descriptions** - Help LLM understand parameters

## Registration

```python
# In your tool module
def register_tools(agent: Agent[Deps, str]) -> None:
    agent.tool(tool_my_action)

# In agent_instance.py
from src.agents.tools import my_tools
my_tools.register_tools(agent_instance)
```

## Deps Structure

```python
@dataclass
class Deps:
    db: PocketBase
    user_id: str
    user_phone: str
    user_name: str
    user_role: str
    current_time: datetime
```

Built before agent run via `build_deps(db=..., user_phone=...)`.
