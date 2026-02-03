# Creating an Agent

This guide provides step-by-step instructions for creating a new Pydantic AI agent.

## Overview

Creating a new agent involves:

1. Creating tool parameter models (Pydantic models)
2. Implementing tool functions with error handling
3. Registering tools with the agent
4. Building and running the agent with dependencies

## Step-by-Step Guide

### Step 1: Create Tool Parameter Models

Define Pydantic models for each tool's parameters:

```python
# src/agents/tools/custom_tools.py

from pydantic import BaseModel, Field

class CreateItem(BaseModel):
    """Parameters for creating a new item."""

    name: str = Field(description="Name of the item")
    description: str = Field(default="", description="Optional description")
    priority: str = Field(
        default="normal",
        description="Priority level: low, normal, or high",
    )
```

### Step 2: Implement Tool Functions

Create async tool functions following the proper signature:

```python
import logging

import logfire
from pydantic_ai import RunContext

from src.agents.base import Deps
from src.services import item_service


logger = logging.getLogger(__name__)

async def tool_create_item(ctx: RunContext[Deps], params: CreateItem) -> str:
    """
    Create a new item.

    Args:
        ctx: Agent runtime context with dependencies
        params: Item creation parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_create_item", name=params.name, priority=params.priority):
            # Create the item using the service
            item_id = await item_service.create_item(
                name=params.name,
                description=params.description,
                priority=params.priority,
                user_id=ctx.deps.user_id,
            )

            return f"Created item '{params.name}' (ID: {item_id}) with {params.priority} priority."

    except ValueError as e:
        logger.warning("Item creation failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_create_item", extra={"error": str(e)})
        return "Error: Unable to create item. Please try again."
```

### Step 3: Register Tools

Create a `register_tools` function to register tools with the agent:

```python
from pydantic_ai import Agent
from src.agents.base import Deps

def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent."""
    agent.tool(tool_create_item)
```

### Step 4: Register Tools Module

Add your tool module to the agent initialization in
`src/agents/agent_instance.py`:

```python
# In _register_all_tools function
from src.agents.tools import custom_tools  # Import your module

def _register_all_tools(agent_instance: Agent[Deps, str]) -> None:
    """Register all tool modules with the agent."""
    # Existing tool registrations...
    analytics_tools.register_tools(agent_instance)
    chore_tools.register_tools(agent_instance)
    # ... more tools ...

    # Add your custom tools
    custom_tools.register_tools(agent_instance)
```

### Step 5: Build Dependencies

Create a function to build dependencies for your agent:

```python
# src/agents/custom_agent.py

from src.agents.base import Deps
from datetime import datetime
from pocketbase import PocketBase

async def build_deps(*, db: PocketBase, user_phone: str) -> Deps | None:
    """
    Build dependencies for agent execution.

    Args:
        db: PocketBase database connection
        user_phone: Phone number of the user

    Returns:
        Deps object or None if user not found
    """
    # Look up user by phone number
    user = await user_service.get_user_by_phone(phone=user_phone)
    if not user:
        return None

    # Build dependencies
    return Deps(
        db=db,
        user_id=user["id"],
        user_phone=user["phone"],
        user_name=user["name"],
        user_role=user["role"],
        current_time=datetime.now(),
    )
```

### Step 6: Run the Agent

Create a function to run the agent with dependencies:

```python
from src.agents.agent_instance import get_agent

async def run_agent(*, user_message: str, deps: Deps) -> str:
    """
    Run the agent with the given message and context.

    Args:
        user_message: The message from the user
        deps: The injected dependencies (db, user info, current time)

    Returns:
        The agent's response as a string
    """
    # Get agent instance
    agent = get_agent()

    # Define system prompt
    instructions = (
        f"You are a helpful assistant for user {deps.user_name}. "
        f"Current time: {deps.current_time.isoformat()}"
    )

    # Run the agent
    result = await agent.run(
        user_message,
        deps=deps,
        message_history=[],
        instructions=instructions,
    )

    return result.output
```

### Step 7: Test the Agent

Test your agent with sample messages:

```python
# Test in a script or REPL
async def test_agent():
    """Test the agent with sample input."""
    # Get database connection
    db = get_db_client()

    # Build dependencies
    deps = await build_deps(db=db, user_phone="+1234567890")

    # Run agent
    response = await run_agent(
        user_message="Create a high priority item called 'Urgent task'",
        deps=deps,
    )

    print(response)  # Should show success message
```

## Complete Example: Notification Agent

Here's a complete example of a notification agent with tools:

### Tool Parameter Models

```python
# src/agents/tools/notification_tools.py

from pydantic import BaseModel, Field

class SendNotification(BaseModel):
    """Parameters for sending a notification."""

    recipient_phone: str = Field(description="Phone number of recipient (E.164 format)")
    message: str = Field(description="Notification message to send")
    priority: str = Field(
        default="normal",
        description="Priority: low, normal, or high",
    )


class GetNotifications(BaseModel):
    """Parameters for retrieving notifications."""

    status: str | None = Field(
        default=None,
        description="Filter by status: pending, sent, or failed",
    )
    limit: int = Field(default=10, description="Maximum number of notifications to retrieve")
```

### Tool Functions

```python
import logging

import logfire
from pydantic_ai import RunContext

from src.agents.base import Deps
from src.services import notification_service


logger = logging.getLogger(__name__)


async def tool_send_notification(ctx: RunContext[Deps], params: SendNotification) -> str:
    """
    Send a notification to a user.

    Args:
        ctx: Agent runtime context with dependencies
        params: Notification parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span(
            "tool_send_notification",
            recipient=params.recipient_phone,
            priority=params.priority,
        ):
            # Send the notification
            notification_id = await notification_service.send_notification(
                recipient_phone=params.recipient_phone,
                message=params.message,
                priority=params.priority,
                sender_id=ctx.deps.user_id,
            )

            return (
                f"Notification sent to {params.recipient_phone} "
                f"(ID: {notification_id}, Priority: {params.priority})"
            )

    except ValueError as e:
        logger.warning("Notification send failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_send_notification", extra={"error": str(e)})
        return "Error: Unable to send notification. Please try again."


async def tool_get_notifications(ctx: RunContext[Deps], params: GetNotifications) -> str:
    """
    Retrieve notifications for the current user.

    Args:
        ctx: Agent runtime context with dependencies
        params: Query parameters

    Returns:
        Formatted list of notifications
    """
    try:
        with logfire.span("tool_get_notifications", status=params.status, limit=params.limit):
            # Get notifications
            notifications = await notification_service.get_user_notifications(
                user_id=ctx.deps.user_id,
                status=params.status,
                limit=params.limit,
            )

            if not notifications:
                return "No notifications found."

            # Format notifications
            lines = [f"Notifications for {ctx.deps.user_name}:"]
            for notif in notifications:
                status_icon = "✓" if notif["status"] == "sent" else "✗"
                lines.append(
                    f"{status_icon} [{notif['priority'].upper()}] {notif['message']} "
                    f"({notif['created_at']})"
                )

            return "\n".join(lines)

    except Exception as e:
        logger.error("Unexpected error in tool_get_notifications", extra={"error": str(e)})
        return "Error: Unable to retrieve notifications. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent."""
    agent.tool(tool_send_notification)
    agent.tool(tool_get_notifications)
```

### Agent Usage

```python
# Example usage in a FastAPI route
from fastapi import APIRouter, BackgroundTasks
from src.core import db_client
from src.agents.custom_agent import build_deps, run_agent

router = APIRouter()

@router.post("/chat")
async def chat(message: str, user_phone: str, background_tasks: BackgroundTasks):
    """Handle chat message from user."""
    # Build dependencies
    deps = await build_deps(db=db_client.get_client(), user_phone=user_phone)
    if not deps:
        return {"error": "User not found"}

    # Run agent in background task
    async def process_message():
        response = await run_agent(user_message=message, deps=deps)
        # Send response via WhatsApp...

    background_tasks.add_task(process_message)

    return {"status": "processing"}
```

## Common Patterns

### Fuzzy Matching

For user-friendly tool parameters, implement fuzzy matching:

```python
def _fuzzy_match_item(items: list[dict], query: str) -> dict | None:
    """Fuzzy match an item by name."""
    query_lower = query.lower().strip()

    # Exact match
    for item in items:
        if item["name"].lower() == query_lower:
            return item

    # Contains match
    for item in items:
        if query_lower in item["name"].lower():
            return item

    return None
```

### User Context

Always use user context from dependencies:

```python
async def tool_with_context(ctx: RunContext[Deps], params: SomeParams) -> str:
    """Tool that uses user context."""
    # Access user information
    user_name = ctx.deps.user_name
    user_id = ctx.deps.user_id
    user_role = ctx.deps.user_role

    # Use context in operations
    return f"Operation performed by {user_name} ({user_role})"
```

### Transaction Support

Use database transactions for multi-step operations:

```python
async def tool_transactional(ctx: RunContext[Deps], params: SomeParams) -> str:
    """Tool with transaction support."""
    try:
        # Use transaction
        async with ctx.deps.db.transaction():
            # Multiple operations
            await ctx.deps.db.create("records1", {...})
            await ctx.deps.db.create("records2", {...})

            return "Transaction completed successfully"
    except Exception as e:
        return "Error: Transaction failed, all changes rolled back"
```

## Verification Checklist

Before deploying a new agent or tool:

- [ ] All tools use `RunContext[Deps]` for dependencies
- [ ] All tools return error strings, not exceptions
- [ ] All error messages start with "Error: "
- [ ] All tools have logging with Logfire spans
- [ ] All tools are registered via `register_tools` function
- [ ] Tool parameter models have Field descriptions
- [ ] Tools use `ctx.deps` for database operations
- [ ] User context is used appropriately
- [ ] Tools are type-annotated with return type `-> str`
- [ ] Type checking passes: `uv run ty check src/agents/`
- [ ] Tests pass: `uv run pytest`
