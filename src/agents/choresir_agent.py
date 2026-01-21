"""Main Pydantic AI agent for choresir household management."""

import logging
import re
import secrets
from datetime import datetime

import logfire
from pocketbase import PocketBase

from src.agents.agent_instance import get_agent
from src.agents.base import Deps
from src.agents.retry_handler import get_retry_handler
from src.core import admin_notifier, db_client
from src.core.config import settings
from src.core.errors import classify_agent_error
from src.domain.user import User, UserStatus
from src.services import session_service, user_service


logger = logging.getLogger(__name__)


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


async def handle_unknown_user(*, user_phone: str, message_text: str) -> str:
    """
    Handle message from unknown user.

    Checks if the message contains join credentials and processes them.
    Otherwise returns an onboarding prompt.

    Args:
        user_phone: Phone number of unknown user
        message_text: The message text from the user

    Returns:
        Join success message or onboarding prompt
    """
    # Try to parse join request: Code: XXX, Password: YYY, Name: ZZZ
    # Pattern matches case-insensitive and handles various formatting
    # Supports quoted passwords for spaces/commas: Password: "my pass"
    pattern = r'code:\s*([A-Z0-9]+).*?password:\s*(?:"([^"]+)|([^\s,]+)).*?name:\s*(.+?)(?:\s*$|\.)'
    match = re.search(pattern, message_text, re.IGNORECASE | re.DOTALL)

    if match:
        house_code = match.group(1).strip()
        # Password is in group 2 (quoted) or group 3 (unquoted)
        password = (match.group(2) or match.group(3)).strip()
        name = match.group(4).strip()

        # Attempt to process the join request
        try:
            await user_service.request_join(
                phone=user_phone,
                name=name,
                house_code=house_code,
                password=password,
            )

            return (
                f"Welcome, {name}! "
                f"Your membership request has been submitted. "
                f"An admin will review your request shortly."
            )
        except ValueError as e:
            # Invalid credentials
            logger.warning(f"Join request failed for {user_phone}: {e}")
            return (
                f"Sorry, I couldn't process your join request: {e}\n\n"
                "Please check your house code and password and try again."
            )
        except Exception as e:
            # Unexpected error
            logger.error(f"Unexpected error processing join request for {user_phone}: {e}")
            return "Sorry, an error occurred while processing your join request. Please try again later."

    # No join request detected, return onboarding prompt
    house_name = settings.house_name or "the house"
    return (
        "Welcome! You're not yet a member of this household.\n\n"
        f"To join, send the command:\n"
        f"/house join {house_name}\n\n"
        "I'll guide you through the rest step by step."
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


async def handle_house_join(phone: str, house_name: str) -> str:
    """
    Handle /house join {house_name} command.

    Steps:
    1. Check if user is already a member
    2. Validate house_name matches configured house (case-insensitive)
    3. Create join session with step="awaiting_password"
    4. Return password prompt message

    Args:
        phone: User's phone number in E.164 format
        house_name: House name provided by user

    Returns:
        Response message for user
    """
    # Guard: Validate house name is configured
    if not settings.house_name:
        logger.error("House name not configured in settings")
        return "Sorry, house joining is not available at this time. Please contact an administrator."

    # Guard: Check if user is already a member
    existing_user = await user_service.get_user_by_phone(phone=phone)
    if existing_user and existing_user.get("status") == UserStatus.ACTIVE:
        return "You're already a member of this household!"

    # Guard: Validate house name matches configured value (case-insensitive)
    if house_name.lower() != settings.house_name.lower():
        return "Invalid house name. Please check and try again."

    # Create join session with initial state
    await session_service.create_session(
        phone=phone,
        house_name=house_name,
        step="awaiting_password",
    )

    # Return password prompt
    return "Please provide the house password:"


async def handle_join_password_step(phone: str, password: str) -> str:
    """
    Handle password submission during join flow.

    Steps:
    1. Get session for phone (returns None if expired)
    2. Check rate limiting (5 second delay)
    3. Validate password with constant-time comparison
    4. On failure: increment attempts, return error
    5. On success: update session to "awaiting_name", return name prompt

    Args:
        phone: User's phone number in E.164 format
        password: Password submitted by user

    Returns:
        Response message for user
    """
    # Get session (returns None if expired)
    session = await session_service.get_session(phone=phone)
    if not session:
        return "Your session has expired. Please restart by typing '/house join {house_name}'."

    # Check rate limiting
    if session_service.is_rate_limited(session=session):
        return "Please wait a few seconds before trying again."

    # Validate password is configured
    if not settings.house_password:
        logger.error("House password not configured in settings")
        return "Sorry, house joining is not available at this time. Please contact an administrator."

    # Validate password with constant-time comparison (prevents timing attacks)
    is_valid = secrets.compare_digest(
        password.encode("utf-8"),
        settings.house_password.encode("utf-8"),
    )

    if not is_valid:
        # Increment attempt counter and update last_attempt_at
        await session_service.increment_password_attempts(phone=phone)
        return f"Invalid password. Please try again or type '/house join {session['house_name']}' to restart."

    # Success! Update session to next step
    await session_service.update_session(
        phone=phone,
        updates={"step": "awaiting_name"},
    )

    # Return name prompt with security reminder
    return (
        "⚠️ For security, please delete your previous message containing the password\n\n"
        "What name would you like to use?"
    )


async def handle_join_name_step(phone: str, name: str) -> str:
    """
    Handle name submission during join flow.

    Steps:
    1. Get session for phone (must be in "awaiting_name" step)
    2. Validate name using User model validator
    3. Create join request via user_service
    4. Delete session (flow complete)
    5. Return welcome message

    Args:
        phone: User's phone number in E.164 format
        name: Name submitted by user

    Returns:
        Response message for user
    """
    # Get session (returns None if expired)
    session = await session_service.get_session(phone=phone)
    if not session:
        house_name = settings.house_name or "the house"
        return f"Your join session has expired. Please restart with '/house join {house_name}'."

    # Verify session is in the correct step
    if session.get("step") != "awaiting_name":
        logger.warning(
            "Session for %s is in wrong step: %s (expected awaiting_name)",
            phone,
            session.get("step"),
        )
        house_name = session.get("house_name", settings.house_name or "the house")
        return f"Something went wrong. Please restart with '/house join {house_name}'."

    # Strip whitespace from name (normalize user input)
    name = name.strip()

    # Validate name using User model validator
    try:
        # Use the User model validator to validate the name
        # We create a temporary User instance just for validation
        User(id="temp", phone=phone, name=name)
    except ValueError as e:
        # Name validation failed - keep session alive for retry
        logger.info("Invalid name submitted by %s: %s", phone, str(e))
        return (
            "That name isn't usable. Please provide a different name (letters, spaces, hyphens, and apostrophes only)."
        )

    # Create join request
    try:
        house_code = session.get("house_name", "")
        if not settings.house_password:
            logger.error("House password not configured in settings")
            await session_service.delete_session(phone=phone)
            return "Sorry, house joining is not available at this time. Please contact an administrator."

        await user_service.request_join(
            phone=phone,
            name=name,
            house_code=house_code,
            password=settings.house_password,
        )
    except Exception as e:
        # Join request failed - delete session anyway (flow is complete)
        logger.error("Failed to create join request for %s: %s", phone, str(e))
        await session_service.delete_session(phone=phone)
        return (
            "Sorry, something went wrong while processing your request. "
            "Please try again later or contact an administrator."
        )

    # Success! Delete session (flow complete)
    await session_service.delete_session(phone=phone)

    # Return welcome message
    return f"Welcome {name}! Your membership request has been submitted. An admin will review shortly."
