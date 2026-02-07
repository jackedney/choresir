"""Group context service for maintaining shared chat history in group chats.

This service stores recent conversation exchanges in group chats to provide context
for follow-up messages, enabling the agent to understand references like 'both', 'that', etc.
"""

import logging
from datetime import datetime, timedelta

from src.core import db_client
from src.core.logging import span


logger = logging.getLogger(__name__)

# How many recent messages to keep per group
MAX_GROUP_MESSAGES = 20

# How long to keep group context messages (in minutes)
GROUP_CONTEXT_TTL_MINUTES = 60

# Maximum length for message content in context display
MAX_CONTEXT_CONTENT_LENGTH = 200


async def add_group_message(
    *,
    group_id: str,
    sender_phone: str,
    sender_name: str,
    content: str,
    is_bot: bool,
) -> None:
    """Record a message in the group context.

    Args:
        group_id: WhatsApp group JID
        sender_phone: Sender's phone number
        sender_name: Sender's display name
        content: Message content
        is_bot: True if this is a bot message, False for user messages

    Raises:
        ValueError: If group_id is empty
    """
    if not group_id:
        raise ValueError("group_id cannot be empty")

    with span("group_context.add_group_message"):
        created_at = datetime.now()
        expires_at = created_at + timedelta(minutes=GROUP_CONTEXT_TTL_MINUTES)

        await db_client.create_record(
            collection="group_context",
            data={
                "group_id": group_id,
                "sender_phone": sender_phone,
                "sender_name": sender_name,
                "content": content,
                "is_bot": is_bot,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        )


async def get_group_context(*, group_id: str) -> list[dict]:
    """Get recent group conversation context.

    Returns up to MAX_GROUP_MESSAGES messages from the last GROUP_CONTEXT_TTL_MINUTES minutes,
    ordered by created_at (oldest first).

    Args:
        group_id: WhatsApp group JID

    Returns:
        List of message dicts with sender_name and content keys

    Raises:
        ValueError: If group_id is empty
    """
    if not group_id:
        raise ValueError("group_id cannot be empty")

    with span("group_context.get_group_context"):
        cutoff_time = datetime.now()

        messages = await db_client.list_records(
            collection="group_context",
            filter_query=(
                f'group_id = "{db_client.sanitize_param(group_id)}" && expires_at >= "{cutoff_time.isoformat()}"'
            ),
            sort="-created_at",
            per_page=MAX_GROUP_MESSAGES,
        )

        # Reverse to get chronological order (oldest first)
        messages.reverse()

        return [{"sender_name": msg["sender_name"], "content": msg["content"]} for msg in messages]


async def cleanup_expired_group_context() -> int:
    """Delete expired group context messages to prevent unbounded database growth.

    Deletes all group_context records where expires_at < now.

    Returns:
        Count of deleted records
    """
    with span("group_context.cleanup_expired_group_context"):
        now = datetime.now().isoformat()

        # Find all expired messages
        expired_messages = await db_client.list_records(
            collection="group_context",
            filter_query=f'expires_at < "{db_client.sanitize_param(now)}"',
        )

        deleted_count = 0

        for message in expired_messages:
            try:
                await db_client.delete_record(
                    collection="group_context",
                    record_id=message["id"],
                )

                deleted_count += 1

                logger.info(
                    "Deleted expired group context message",
                    extra={
                        "message_id": message["id"],
                        "group_id": message["group_id"],
                        "sender_name": message["sender_name"],
                    },
                )
            except Exception as e:
                logger.error(
                    f"Error deleting expired group context message {message['id']}: {e}",
                )

        logger.info("Completed group context cleanup", extra={"deleted_count": deleted_count})

        return deleted_count


def format_group_context_for_prompt(context: list[dict]) -> str:
    """Format group context for inclusion in system prompt.

    Args:
        context: List of message dicts with 'sender_name' and 'content'

    Returns:
        Formatted string for system prompt, or empty string if no context
    """
    if not context:
        return ""

    lines = [
        "",
        "## RECENT GROUP CONVERSATION",
        "",
        "Recent messages in this group chat (for context on shared references):",
        "",
    ]

    for msg in context:
        # Truncate long messages
        content = msg["content"]
        if len(content) > MAX_CONTEXT_CONTENT_LENGTH:
            content = content[:MAX_CONTEXT_CONTENT_LENGTH] + "..."
        lines.append(f"[{msg['sender_name']}]: {content}")

    lines.append("")
    lines.append(
        "If anyone's current message references something from this context "
        "(e.g., 'both', 'that', '1 and 2', 'the first one'), use this history to understand their intent."
    )

    return "\n".join(lines)
