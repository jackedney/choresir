"""Main Pydantic AI agent for choresir household management."""

import logging
from datetime import datetime

import logfire

from src.agents.agent_instance import get_agent
from src.agents.base import Deps
from src.agents.retry_handler import get_retry_handler
from src.core import admin_notifier, db_client
from src.core.errors import classify_agent_error
from src.domain.update_models import UserStatusUpdate
from src.domain.user import UserStatus
from src.services import user_service
from src.services.house_config_service import get_house_config


logger = logging.getLogger(__name__)


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
- Pantry & Shopping: Manage inventory, add items to shopping list, checkout after shopping
- Stats: Get personal stats and ranking (triggers: "stats", "score", "how am I doing")
- Personal Chores: Private individual task tracking (see below)

Use tools to perform actions. Always confirm understanding before using destructive tools.

## Personal Chores vs Household Chores

You manage TWO separate systems:

1. **Household Chores**: Shared responsibilities tracked on the leaderboard
   - Commands: "Done dishes", "Create chore", "Stats"
   - Visible to all household members
   - Require verification from other members

2. **Personal Chores**: Private individual tasks
   - Commands: "/personal add", "/personal done", "/personal stats"
   - Completely private (only owner can see)
   - Optional accountability partner for verification
   - NOT included in household leaderboard or reports

## Command Routing Rules

- If message starts with "/personal", route to personal chore tools
- If message says "done X" or "log X", check for name collision:
  1. Search household chores for "X"
  2. Search user's personal chores for "X"
  3. If BOTH match, ask: "Did you mean household [X] or your personal [X]?"
  4. If only one matches, proceed with that one
- For stats/list commands without "/personal", default to household
- For create/add commands without "/personal", default to household

## Personal Chore Disambiguation

When a user says "Done gym":
- Check if "gym" matches any household chore
- Check if "gym" matches any of the user's personal chores
- If BOTH match:
  ```
  Bot: "I found both a household chore 'Gym' and your personal chore 'Gym'.
       Which one did you complete? Reply 'household' or 'personal'."
  ```
- Remember the context of this question for the next user message
- When user replies "household" or "personal", complete the appropriate chore

## Personal Chore Privacy Rules

CRITICAL: Personal chores are completely private.
- NEVER mention another user's personal chores in responses
- NEVER show personal chore completions in household reports
- Accountability partners can only verify, not view stats
- All personal chore notifications must be sent via DM only
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
    instructions = _build_system_prompt(
        user_name=deps.user_name,
        user_phone=deps.user_phone,
        user_role=deps.user_role,
        current_time=deps.current_time.isoformat(),
        member_list=member_list,
    )

    try:
        # Get agent instance (lazy initialization)
        agent = get_agent()
        retry_handler = get_retry_handler()

        # Define the agent execution function for retry wrapper
        async def execute_agent() -> str:
            with logfire.span("choresir_agent_run", user_id=deps.user_id):
                result = await agent.run(
                    user_message,
                    deps=deps,
                    message_history=[],
                    instructions=instructions,
                )
                return result.output

        # Run the agent with intelligent retry logic
        return await retry_handler.execute_with_retry(execute_agent)
    except Exception as e:
        # Classify the error and get user-friendly message
        error_category, user_message = classify_agent_error(e)

        # Log the error with category information
        logfire.error(
            "Agent execution failed",
            error=str(e),
            error_category=error_category.value,
        )

        # Notify admins for critical errors
        if admin_notifier.should_notify_admins(error_category):
            try:
                timestamp = datetime.now().isoformat()
                message = (
                    f"⚠️ OpenRouter quota exceeded. User {deps.user_name} ({deps.user_phone}) affected at {timestamp}"
                )
                await admin_notifier.notify_admins(
                    message=message,
                    severity="critical",
                )
            except Exception as notify_error:
                logger.error(f"Failed to notify admins of quota exceeded error: {notify_error}")

        return user_message


async def build_deps(*, user_phone: str) -> Deps | None:
    """
    Build dependencies for agent execution with user context.

    Args:
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
        user_id=user["id"],
        user_phone=user["phone"],
        user_name=user["name"],
        user_role=user["role"],
        current_time=datetime.now(),
    )


async def get_member_list() -> str:
    """
    Get formatted list of household members.

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


async def handle_unknown_user(*, user_phone: str, message_text: str) -> str:
    """Handle unknown users with pending-invite confirmation."""
    # Check for pending invite (web admin flow)
    pending_invite = await db_client.get_first_record(
        collection="pending_invites",
        filter_query=f'phone = "{db_client.sanitize_param(user_phone)}"',
    )

    if pending_invite:
        # Normalize message text for case-insensitive comparison
        normalized_message = message_text.strip().upper()

        if normalized_message == "YES":
            # Get user record
            user = await user_service.get_user_by_phone(phone=user_phone)
            if user:
                # Update user status to active
                await db_client.update_record(
                    collection="users",
                    record_id=user["id"],
                    data=UserStatusUpdate(status="active").model_dump(exclude_none=True),
                )
                logger.info("invite_confirmed", extra={"user_phone": user_phone})

                # Delete pending invite record
                await db_client.delete_record(
                    collection="pending_invites",
                    record_id=pending_invite["id"],
                )

                # Get house config for welcome message
                config = await get_house_config()
                house_name = config.name

                return f"Welcome to {house_name}! Your membership is now active."

            logger.warning("user_not_found_for_pending_invite", extra={"user_phone": user_phone})
            return "Sorry, there was an error processing your invite. Please contact an admin."

        # Message is not YES - instruct user to reply YES
        return "To confirm your invitation, please reply YES"

    # No pending invite - user is not a member
    return "You are not a member of this household. Please contact an admin to request an invite."


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
