"""Main Pydantic AI agent for choresir household management."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from pydantic_ai.messages import ModelMessage

from src.agents.agent_instance import get_agent
from src.agents.base import Deps
from src.agents.retry_handler import get_retry_handler
from src.core import admin_notifier, config, db_client
from src.core.errors import classify_agent_error
from src.core.module_registry import get_modules
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


def _build_system_prompt(ctx: PromptContext) -> str:
    """Build the system prompt with composed sections from base and modules.

    The prompt is composed of:
    1. Base section: Core directives, current context, member list (domain-agnostic)
    2. Module sections: Domain-specific prompt sections from registered modules
    3. Dynamic context: Pending workflows and conversation/group history

    Args:
        ctx: Prompt context containing user info, time, member list, and dynamic context

    Returns:
        Complete system prompt as a string
    """
    # Base prompt section (domain-agnostic)
    bot_name = config.settings.bot_name
    bot_description = config.settings.bot_description
    base_prompt = f"""You are {bot_name}, a {bot_description}. Your role is strictly functional.

CORE DIRECTIVES:
1. No fluff. Be concise. Use WhatsApp-friendly formatting (max 2-3 sentences).
2. Strict neutrality. No praise, no judgment. Report facts only.
3. Entity anchoring. Always reference entities by ID/phone number, not assumptions.
4. Confirm before destructive actions (delete task, ban user).
5. If ambiguous, ask clarifying questions with options.

CURRENT CONTEXT:
- User: {ctx.user_name} ({ctx.user_phone})
- Role: {ctx.user_role}
- Time: {ctx.current_time}

HOUSEHOLD MEMBERS:
{ctx.member_list}

"""

    # Collect module sections from all registered modules
    module_sections = []
    modules = get_modules()
    for module in modules.values():
        section = module.get_system_prompt_section()
        if section:
            module_sections.append(section)

    # Combine all sections
    dynamic_context = ctx.pending_context + ctx.conversation_context
    prompt_parts = [base_prompt, *module_sections, dynamic_context]
    return "\n".join(prompt_parts)


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
            logger.info("choresir_agent_run", extra={"user_id": deps.user_id})
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
        logger.error(
            "Agent execution failed",
            extra={"error": str(e), "error_category": error_category.value},
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


async def build_deps(*, db: object, user_phone: str) -> Deps | None:
    """
    Build dependencies for agent execution with user context.

    Args:
        db: Database connection (unused, retained for API compatibility)
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


async def get_member_list(*, _db: object) -> str:
    """
    Get formatted list of household members.

    Args:
        db: Database connection (unused, retained for API compatibility)

    Returns:
        Formatted member list string
    """
    members = await db_client.list_records(
        collection="members",
        sort="name ASC",
    )

    if not members:
        return "No members yet."

    # Format member list
    lines = []
    for member in members:
        role_indicator = " (admin)" if member["role"] == "admin" else ""
        status_indicator = " (awaiting name)" if member["status"] == UserStatus.PENDING_NAME else ""
        lines.append(f"- {member['name']} ({member['phone']}){role_indicator}{status_indicator}")

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
