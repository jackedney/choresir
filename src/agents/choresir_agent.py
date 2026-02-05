"""Main Pydantic AI agent for choresir household management."""

import logging
import re
from datetime import datetime

import logfire
from pocketbase import PocketBase

from src.agents.agent_instance import get_agent
from src.agents.base import Deps
from src.agents.retry_handler import get_retry_handler
from src.core import admin_notifier, db_client
from src.core.errors import classify_agent_error
from src.domain.user import User, UserStatus
from src.services import session_service, user_service
from src.services.house_config_service import get_house_config, validate_house_password


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

    Checks for pending invites, join sessions, and join credentials.
    Returns appropriate response based on context.

    Args:
        user_phone: Phone number of unknown user
        message_text: The message text from the user

    Returns:
        Join success message, invite confirmation response, or onboarding prompt
    """
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
                    data={"status": "active"},
                )
                logger.info("Confirmed invite for user: %s", user_phone)

                # Delete pending invite record
                await db_client.delete_record(
                    collection="pending_invites",
                    record_id=pending_invite["id"],
                )

                # Get house config for welcome message
                config = await get_house_config()
                house_name = config["name"]

                return f"Welcome to {house_name}! Your membership is now active."

            logger.warning("User not found for pending invite: %s", user_phone)
            return "Sorry, there was an error processing your invite. Please contact an admin."

        # Message is not YES - instruct user to reply YES
        return "To confirm your invitation, please reply YES"

    # Check for active join session first
    session = await session_service.get_session(phone=user_phone)

    # Check for /cancel command (before step handlers so it works during any step)
    if re.match(r"^/cancel$", message_text, re.IGNORECASE):
        if session:
            await session_service.delete_session(phone=user_phone)
            return "Join process cancelled. Send '/house join {house_name}' to start again."
        return "Nothing to cancel."

    if session:
        step = session.get("step")
        if step == "awaiting_password":
            return await handle_join_password_step(user_phone, message_text)
        if step == "awaiting_name":
            return await handle_join_name_step(user_phone, message_text)

    # Check for /house join {house_name} command
    house_join_match = re.match(r"^/house\s+join\s+(.+)$", message_text, re.IGNORECASE)
    if house_join_match:
        house_name = house_join_match.group(1).strip()
        return await handle_house_join(phone=user_phone, house_name=house_name)

    # No pending invite, no join session, not a join command - user is not a member
    return "You are not a member of this household. Please contact an admin to request an invite."


async def _handle_legacy_join_or_onboard(user_phone: str, message_text: str) -> str:
    """Handle legacy join format (Code/Password/Name) or return onboarding prompt."""
    # Try to parse join request: Code: XXX, Password: YYY, Name: ZZZ
    # Pattern matches case-insensitive and handles various formatting
    # Supports quoted passwords for spaces/commas: Password: "my pass"
    pattern = r'code:\s*([A-Z0-9]+).*?password:\s*(?:"([^"]+)|([^\s,]+)).*?name:\s*(.+?)(?:\s*$|\.)'
    match = re.search(pattern, message_text, re.IGNORECASE | re.DOTALL)

    if not match:
        # No join request detected, return onboarding prompt
        config = await get_house_config()
        house_name = config["name"]
        return (
            "Welcome! You're not yet a member of this household.\n\n"
            "To join, type:\n"
            f"/house join {house_name}\n\n"
            "You'll then be asked for the password and your preferred name."
        )

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
            f"Welcome, {name}! Your membership request has been submitted. An admin will review your request shortly."
        )
    except ValueError as e:
        logger.warning(f"Join request failed for {user_phone}: {e}")
        return (
            f"Sorry, I couldn't process your join request: {e}\n\n"
            "Please check your house code and password and try again."
        )
    except Exception as e:
        logger.error(f"Unexpected error processing join request for {user_phone}: {e}")
        return "Sorry, an error occurred while processing your join request. Please try again later."


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
    # Guard: Get house config
    config = await get_house_config()
    configured_house_name = config["name"]

    # Guard: Check if user is already a member
    existing_user = await user_service.get_user_by_phone(phone=phone)
    if existing_user and existing_user.get("status") == UserStatus.ACTIVE:
        return "You're already a member of this household!"

    # Guard: Validate house name matches configured value (case-insensitive)
    normalized_house_name = house_name.strip().lower()
    if normalized_house_name != configured_house_name.lower():
        return "Invalid house name. Please check and try again."

    # Create join session with initial state
    # Store original house_name (preserving case) for display purposes
    await session_service.create_session(
        phone=phone,
        house_name=house_name.strip(),
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

    # Validate password using house config
    is_valid = await validate_house_password(password=password)

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
    Handle name submission during join flow (final step).

    Steps:
    1. Get session for phone (returns None if expired)
    2. Verify session is in "awaiting_name" step
    3. Normalize and validate name
    4. Create join request via user_service
    5. Delete session (flow complete)
    6. Return welcome message

    Args:
        phone: User's phone number in E.164 format
        name: Name submitted by user

    Returns:
        Response message for user
    """
    # Get session (returns None if expired)
    session = await session_service.get_session(phone=phone)
    if not session:
        config = await get_house_config()
        house_name = config["name"]
        return f"Your join session has expired. Please restart with '/house join {house_name}'."

    # Verify session is in the correct step
    if session.get("step") != "awaiting_name":
        logger.warning(
            "Session for %s is in wrong step: %s (expected awaiting_name)",
            phone,
            session.get("step"),
        )
        config = await get_house_config()
        house_name = config["name"]
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
        config = await get_house_config()

        if not config["code"] or not config["password"]:
            logger.error("House credentials not configured")
            await session_service.delete_session(phone=phone)
            return "Sorry, house joining is not available at this time. Please contact an administrator."

        await user_service.request_join(
            phone=phone,
            name=name,
            house_code=config["code"],
            password=config["password"],
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
