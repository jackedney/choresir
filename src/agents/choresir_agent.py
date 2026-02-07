"""Main Pydantic AI agent for choresir household management."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

import logfire
from pocketbase import PocketBase
from pydantic_ai.messages import ModelMessage

from src.agents.agent_instance import get_agent
from src.agents.base import Deps
from src.agents.retry_handler import get_retry_handler
from src.core import admin_notifier, db_client
from src.core.errors import classify_agent_error
from src.domain.user import UserStatus
from src.services import user_service, workflow_service
from src.services.conversation_context_service import (
    format_context_for_prompt,
    get_recent_context,
)
from src.services.group_context_service import (
    format_group_context_for_prompt,
    get_group_context,
)


@dataclass
class PromptContext:
    """Context data for building the system prompt."""

    user_name: str
    user_phone: str
    user_role: str
    current_time: str
    member_list: str
    pending_context: str = ""
    conversation_context: str = ""


logger = logging.getLogger(__name__)

# Regex pattern to strip special tokens from LLM output
# These tokens can leak from various models (Qwen, DeepSeek, etc.)
_SPECIAL_TOKEN_PATTERN = re.compile(
    r"<\|(?:FunctionCallEnd|endoftext|im_start|im_end|pad|eos|bos|assistant|user|system)\|>",
    re.IGNORECASE,
)


logger = logging.getLogger(__name__)


def _sanitize_llm_output(text: str) -> str:
    """Remove leaked special tokens from LLM output.

    Some models (Qwen, DeepSeek, etc.) may leak special tokens like
    <|FunctionCallEnd|> into their output. This function strips them.

    Args:
        text: Raw LLM output text

    Returns:
        Sanitized text with special tokens removed
    """
    sanitized = _SPECIAL_TOKEN_PATTERN.sub("", text)
    # Clean up any resulting double spaces or leading/trailing whitespace
    sanitized = re.sub(r"\s{2,}", " ", sanitized)
    return sanitized.strip()


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

## Household Chore Deletion (Two-Step Process)

IMPORTANT: Household chores use a TWO-STEP deletion process:
1. **Request deletion**: Use `tool_request_chore_deletion` - this creates a pending request
2. **Approve deletion**: Another household member must approve using `tool_respond_to_deletion`

When a user asks to delete/remove a HOUSEHOLD chore:
- Use `tool_request_chore_deletion` to initiate the request
- Tell them another member must approve the deletion
- DO NOT use personal chore removal tools for household chores

When a user confirms "yes" to delete household chores:
- If you previously asked about deleting household chores, proceed with the deletion request
- DO NOT route this to personal chore tools

## Personal Chores vs Household Chores

You manage TWO separate systems:

1. **Household Chores**: Shared responsibilities tracked on the leaderboard
   - Commands: "Done dishes", "Create chore", "Delete chore", "Stats"
   - Visible to all household members
   - Require verification from other members
   - Deletion requires approval from another member (two-step process)

2. **Personal Chores**: Private individual tasks
   - Commands: "/personal add", "/personal done", "/personal remove", "/personal stats"
   - Completely private (only owner can see)
   - Optional accountability partner for verification
   - NOT included in household leaderboard or reports
   - Can be removed immediately by owner (no approval needed)

## Command Routing Rules

CRITICAL ROUTING RULES:
- If message starts with "/personal", route to personal chore tools
- If user is confirming a previous question about HOUSEHOLD chores, use HOUSEHOLD tools
- If user is confirming a previous question about PERSONAL chores, use PERSONAL tools
- Check the RECENT CONVERSATION section to understand what the user is confirming

For "done X" or "log X" commands:
  1. Search household chores for "X"
  2. Search user's personal chores for "X"
  3. If BOTH match, ask: "Did you mean household [X] or your personal [X]?"
  4. If only one matches, proceed with that one
- For stats/list commands without "/personal", default to household
- For create/add commands without "/personal", default to household

## Understanding Confirmatory Responses

When a user sends short confirmatory messages like:
- "Yes", "Yeah", "Confirm", "OK" - confirm the most recent pending action
- "1", "2", "1 and 2", "both" - select numbered items from a list you provided
- "the first one", "all of them" - reference items you listed

ALWAYS check the RECENT CONVERSATION section to understand what they're confirming.
If you asked about household chores, confirm with household chore tools.
If you asked about personal chores, confirm with personal chore tools.

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
{pending_context}"""


def _build_system_prompt(ctx: PromptContext) -> str:
    """Build the system prompt with injected context."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        user_name=ctx.user_name,
        user_phone=ctx.user_phone,
        user_role=ctx.user_role,
        current_time=ctx.current_time,
        member_list=ctx.member_list,
        pending_context=ctx.pending_context + ctx.conversation_context,
    )


async def _build_workflow_context(user_id: str) -> str:
    """Build context string for pending workflows.

    Shows workflows initiated by the user (awaiting others) and workflows from others
    that the user can action (approve/reject).

    Args:
        user_id: User ID to check for pending workflows

    Returns:
        Context string to append to system prompt, or empty string if none
    """
    user_workflows = await workflow_service.get_user_pending_workflows(user_id=user_id)
    actionable_workflows = await workflow_service.get_actionable_workflows(user_id=user_id)

    if not user_workflows and not actionable_workflows:
        return ""

    lines = []

    # Section 1: Workflows user initiated (awaiting others)
    if user_workflows:
        lines.extend(["", "## YOUR PENDING REQUESTS", "", "You have requested the following (awaiting approval):"])
        for wf in user_workflows:
            workflow_type = wf["type"].replace("_", " ").title()
            lines.append(f"- {workflow_type}: {wf['target_title']}")

    # Section 2: Workflows from others user can action
    if actionable_workflows:
        lines.extend(["", "## REQUESTS YOU CAN ACTION", "", "You can approve/reject the following:"])
        for idx, wf in enumerate(actionable_workflows, start=1):
            workflow_type = wf["type"].replace("_", " ").title()
            lines.append(f"{idx}. {workflow_type}: {wf['target_title']} (from {wf['requester_name']})")

        lines.extend(["", "User can say: approve 1, reject both, approve all"])

    return "\n".join(lines)


async def run_agent(
    *,
    user_message: str,
    deps: Deps,
    member_list: str,
    message_history: list[ModelMessage] | None = None,
    group_id: str | None = None,
) -> str:
    """
    Run the choresir agent with the given message and context.

    Args:
        user_message: The message from the user
        deps: The injected dependencies (db, user info, current time)
        member_list: Formatted list of household members
        message_history: Optional conversation history for context
        group_id: Optional WhatsApp group ID for shared group context

    Returns:
        The agent's response as a string
    """
    # Build workflow context for this user
    pending_context = await _build_workflow_context(deps.user_id)

    # Build conversation context from recent messages
    # Use group context for group chats, per-user context for DMs
    conversation_context = ""
    if group_id:
        try:
            group_context = await get_group_context(group_id=group_id)
            conversation_context = format_group_context_for_prompt(group_context)
        except Exception as e:
            logger.warning("Failed to get group context: %s", e)
    else:
        try:
            recent_context = await get_recent_context(user_phone=deps.user_phone)
            conversation_context = format_context_for_prompt(recent_context)
        except Exception as e:
            logger.warning("Failed to get conversation context: %s", e)

    # Build system prompt with context
    prompt_ctx = PromptContext(
        user_name=deps.user_name,
        user_phone=deps.user_phone,
        user_role=deps.user_role,
        current_time=deps.current_time.isoformat(),
        member_list=member_list,
        pending_context=pending_context,
        conversation_context=conversation_context,
    )
    instructions = _build_system_prompt(prompt_ctx)

    try:
        # Get agent instance (lazy initialization)
        agent = get_agent()
        retry_handler = get_retry_handler()

        # Use provided message history or empty list
        history = message_history or []

        # Define the agent execution function for retry wrapper
        async def execute_agent() -> str:
            with logfire.span("choresir_agent_run", user_id=deps.user_id):
                result = await agent.run(
                    user_message,
                    deps=deps,
                    message_history=history,
                    instructions=instructions,
                )
                # Sanitize output to remove any leaked special tokens
                return _sanitize_llm_output(result.output)

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
                    f"OpenRouter quota exceeded. User {deps.user_name} ({deps.user_phone}) affected at {timestamp}"
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
        collection="members",
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


async def handle_pending_user(*, user_name: str) -> str:
    """
    Handle message from pending user.

    Args:
        user_name: Name of pending user

    Returns:
        Status message
    """
    return f"Hi {user_name}! Please reply with your name to complete registration."
