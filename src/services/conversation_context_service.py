"""Conversation context service for maintaining chat history per user.

This service stores recent conversation exchanges to provide context
for follow-up messages, enabling the agent to understand references
like "Yes", "1. and 2.", etc.
"""

import logging
from datetime import datetime, timedelta

from src.core import db_client
from src.core.logging import span


logger = logging.getLogger(__name__)

# How many recent messages to keep per user
MAX_CONTEXT_MESSAGES = 10

# How long to keep context messages (in minutes)
CONTEXT_TTL_MINUTES = 30

# Maximum length for message content in context display
MAX_CONTEXT_CONTENT_LENGTH = 200


async def add_user_message(*, user_phone: str, content: str) -> None:
    """Record a user message in the conversation context.

    Args:
        user_phone: User's phone number
        content: Message content
    """
    with span("conversation_context.add_user_message"):
        await db_client.create_record(
            collection="conversation_context",
            data={
                "user_phone": user_phone,
                "role": "user",
                "content": content,
                "timestamp": datetime.now().isoformat(),
            },
        )
        # Clean up old messages for this user
        await _cleanup_old_messages(user_phone=user_phone)


async def add_assistant_message(*, user_phone: str, content: str) -> None:
    """Record an assistant message in the conversation context.

    Args:
        user_phone: User's phone number
        content: Message content
    """
    with span("conversation_context.add_assistant_message"):
        await db_client.create_record(
            collection="conversation_context",
            data={
                "user_phone": user_phone,
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now().isoformat(),
            },
        )
        # Clean up old messages for this user
        await _cleanup_old_messages(user_phone=user_phone)


async def get_recent_context(*, user_phone: str) -> list[dict]:
    """Get recent conversation context for a user.

    Returns messages from the last CONTEXT_TTL_MINUTES minutes,
    up to MAX_CONTEXT_MESSAGES.

    Args:
        user_phone: User's phone number

    Returns:
        List of message dicts with 'role' and 'content' keys, oldest first
    """
    with span("conversation_context.get_recent_context"):
        cutoff_time = datetime.now() - timedelta(minutes=CONTEXT_TTL_MINUTES)

        messages = await db_client.list_records(
            collection="conversation_context",
            filter_query=(
                f'user_phone = "{db_client.sanitize_param(user_phone)}" && timestamp >= "{cutoff_time.isoformat()}"'
            ),
            sort="timestamp DESC",
            per_page=MAX_CONTEXT_MESSAGES,
        )

        # Reverse to get chronological order (oldest first)
        messages.reverse()

        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]


async def _cleanup_old_messages(*, user_phone: str) -> None:
    """Remove old messages beyond the retention limit.

    Keeps only the most recent MAX_CONTEXT_MESSAGES for the user,
    and removes any messages older than CONTEXT_TTL_MINUTES.

    Args:
        user_phone: User's phone number
    """
    try:
        cutoff_time = datetime.now() - timedelta(minutes=CONTEXT_TTL_MINUTES)

        # Get all messages for this user
        all_messages = await db_client.list_records(
            collection="conversation_context",
            filter_query=f'user_phone = "{db_client.sanitize_param(user_phone)}"',
            sort="timestamp DESC",
        )

        # Delete messages beyond the limit or older than TTL
        for i, msg in enumerate(all_messages):
            should_delete = False

            # Beyond count limit
            if i >= MAX_CONTEXT_MESSAGES:
                should_delete = True

            # Older than TTL
            msg_timestamp = msg.get("timestamp", "")
            if msg_timestamp:
                try:
                    msg_time = datetime.fromisoformat(msg_timestamp.replace("Z", "+00:00").split("+")[0])
                    if msg_time < cutoff_time:
                        should_delete = True
                except (ValueError, TypeError):
                    pass

            if should_delete:
                try:
                    await db_client.delete_record(
                        collection="conversation_context",
                        record_id=msg["id"],
                    )
                except Exception as e:
                    logger.warning("Failed to delete old context message %s: %s", msg["id"], e)

    except Exception as e:
        # Don't fail the main operation if cleanup fails
        logger.warning("Failed to cleanup old context messages for %s: %s", user_phone, e)


async def clear_context(*, user_phone: str) -> None:
    """Clear all conversation context for a user.

    Args:
        user_phone: User's phone number
    """
    with span("conversation_context.clear_context"):
        try:
            messages = await db_client.list_records(
                collection="conversation_context",
                filter_query=f'user_phone = "{db_client.sanitize_param(user_phone)}"',
            )

            for msg in messages:
                await db_client.delete_record(
                    collection="conversation_context",
                    record_id=msg["id"],
                )
        except Exception as e:
            logger.warning("Failed to clear context for %s: %s", user_phone, e)


def format_context_for_prompt(context: list[dict]) -> str:
    """Format conversation context for inclusion in system prompt.

    Args:
        context: List of message dicts with 'role' and 'content'

    Returns:
        Formatted string for system prompt, or empty string if no context
    """
    if not context:
        return ""

    lines = [
        "",
        "## RECENT CONVERSATION",
        "",
        "Recent messages in this conversation (for context on follow-up references):",
        "",
    ]

    for msg in context:
        role_label = "User" if msg["role"] == "user" else "You"
        # Truncate long messages
        content = msg["content"]
        if len(content) > MAX_CONTEXT_CONTENT_LENGTH:
            content = content[:MAX_CONTEXT_CONTENT_LENGTH] + "..."
        lines.append(f"{role_label}: {content}")

    lines.append("")
    lines.append(
        "If the user's current message references something from this context "
        "(e.g., 'Yes', '1 and 2', 'the first one'), use this history to understand their intent."
    )

    return "\n".join(lines)
