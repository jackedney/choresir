"""Main Pydantic AI agent for choresir household management."""

from datetime import datetime

import logfire
from pocketbase import PocketBase
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel

from src.agents.base import Deps
from src.core import db_client
from src.core.config import settings
from src.domain.user import UserStatus
from src.services import user_service

# Configure Logfire for observability
logfire.configure(token=settings.logfire_token)

# System prompt template
SYSTEM_PROMPT_TEMPLATE = """You are choresir, a household chore management assistant. Your role is strictly functional.

CORE DIRECTIVES:
1. No fluff. Be concise. Use WhatsApp-friendly formatting (max 2-3 sentences).
2. Strict neutrality. No praise, no judgment. Report facts only.
3. Entity anchoring. Always reference entities by ID/phone number, not assumptions.
4. Confirm before destructive actions (delete chore, ban user).
5. If ambiguous, ask clarifying questions with options.

CURRENT CONTEXT:
- User: {user_name} ({user_phone})
- Role: {user_role}
- Time: {current_time}

HOUSEHOLD MEMBERS:
{member_list}

AVAILABLE ACTIONS:
You have access to tools for:
- Onboarding: Request to join household, approve members (admin only)
- Chore Management: Define new chores, log completions
- Verification: Verify chore completions, query status
- Analytics: Get leaderboards, completion rates, overdue chores

Use tools to perform actions. Always confirm understanding before using destructive tools.
"""


def _build_system_prompt(
    *, user_name: str, user_phone: str, user_role: str, current_time: str, member_list: str
) -> str:
    """Build the system prompt with injected context."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        user_name=user_name,
        user_phone=user_phone,
        user_role=user_role,
        current_time=current_time,
        member_list=member_list,
    )


# Initialize the agent with OpenRouter
model = OpenRouterModel(
    model_name=settings.model_id,
    api_key=settings.openrouter_api_key,
)

# Create the agent
agent: Agent[Deps, str] = Agent(
    model=model,
    deps_type=Deps,
    retries=2,
)

# Import tools to register them with the agent
# This must happen after agent creation
from src.agents.tools import analytics_tools, chore_tools, onboarding_tools, verification_tools  # noqa: F401, E402


async def run_agent(*, user_message: str, deps: Deps, member_list: str) -> str:
    """
    Run the choresir agent with the given message and context.

    Args:
        user_message: The message from the user
        deps: The injected dependencies (db, user info, current time)
        member_list: Formatted list of household members

    Returns:
        The agent's response as a string
    """
    # Build system prompt with context
    system_prompt = _build_system_prompt(
        user_name=deps.user_name,
        user_phone=deps.user_phone,
        user_role=deps.user_role,
        current_time=deps.current_time.isoformat(),
        member_list=member_list,
    )

    try:
        # Run the agent with Logfire tracing
        with logfire.span("choresir_agent_run", user_id=deps.user_id):
            result = await agent.run(
                user_message,
                deps=deps,
                message_history=[],
                system_prompt=system_prompt,
            )
            return result.data
    except Exception as e:
        logfire.error("Agent execution failed", error=str(e))
        return f"Error: Unable to process request. {str(e)}"


async def build_deps(*, db: PocketBase, user_phone: str) -> Deps | None:
    """
    Build dependencies for agent execution with user context.

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


async def get_member_list(*, _db: PocketBase) -> str:
    """
    Get formatted list of household members.

    Args:
        db: PocketBase database connection

    Returns:
        Formatted member list string
    """
    # Get all active members
    members = await db_client.list_records(
        collection="users",
        filter_query=f'status = "{UserStatus.ACTIVE}"',
        sort="+name",
    )

    if not members:
        return "No active members."

    # Format member list
    lines = []
    for member in members:
        role_indicator = " (admin)" if member["role"] == "admin" else ""
        lines.append(f"- {member['name']} ({member['phone']}){role_indicator}")

    return "\n".join(lines)


async def handle_unknown_user(*, _user_phone: str) -> str:
    """
    Handle message from unknown user.

    Args:
        user_phone: Phone number of unknown user

    Returns:
        Onboarding prompt message
    """
    return (
        f"Welcome! You're not yet a member of this household.\n\n"
        f"To join, please provide:\n"
        f"1. House code\n"
        f"2. House password\n"
        f"3. Your preferred name\n\n"
        f"Say something like: 'I want to join. Code: XXXX, Password: YYYY, Name: Your Name'"
    )


async def handle_pending_user(*, user_name: str) -> str:
    """
    Handle message from pending user.

    Args:
        user_name: Name of pending user

    Returns:
        Status message
    """
    return f"Hi {user_name}! Your membership is awaiting approval from an admin."


async def handle_banned_user(*, user_name: str) -> str:
    """
    Handle message from banned user.

    Args:
        user_name: Name of banned user

    Returns:
        Rejection message
    """
    return f"Hi {user_name}. Your access to this household has been revoked."
