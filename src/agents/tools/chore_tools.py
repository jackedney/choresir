"""Chore management tools for the choresir agent."""

import logging

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.domain.chore import ChoreState
from src.services import chore_service, personal_chore_service, user_service, verification_service


logger = logging.getLogger(__name__)


class DefineChore(BaseModel):
    """Parameters for defining a new chore."""

    title: str = Field(description="Chore title (e.g., 'Take out trash')")
    recurrence: str = Field(description="Recurrence string (e.g., 'every 3 days' or CRON format)")
    assignee_phone: str | None = Field(
        default=None,
        description="Phone number of user to assign chore to (None for unassigned)",
    )
    description: str = Field(default="", description="Optional detailed description")


class LogChore(BaseModel):
    """Parameters for logging a chore completion."""

    chore_title_fuzzy: str = Field(description="Chore title or partial match (fuzzy search)")
    notes: str | None = Field(default=None, description="Optional notes about completion")
    is_swap: bool = Field(
        default=False,
        description="True if this is a Robin Hood swap (one user doing another's chore)",
    )


def _fuzzy_match_chore(chores: list[dict], title_query: str) -> dict | None:
    """
    Fuzzy match a chore by title.

    Args:
        chores: List of chore records
        title_query: User's search query

    Returns:
        Best matching chore or None
    """
    title_lower = title_query.lower().strip()

    # Exact match
    for chore in chores:
        if chore["title"].lower() == title_lower:
            return chore

    # Contains match
    for chore in chores:
        if title_lower in chore["title"].lower():
            return chore

    # Partial word match
    query_words = set(title_lower.split())
    for chore in chores:
        chore_words = set(chore["title"].lower().split())
        if query_words & chore_words:  # Intersection
            return chore

    return None


async def tool_define_chore(_ctx: RunContext[Deps], params: DefineChore) -> str:
    """
    Define a new chore with recurrence schedule.

    Args:
        ctx: Agent runtime context with dependencies
        params: Chore definition parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_define_chore", title=params.title):
            # If assignee phone is provided, look up user ID
            assignee_id = None
            if params.assignee_phone:
                user = await user_service.get_user_by_phone(phone=params.assignee_phone)
                if not user:
                    return f"Error: User with phone {params.assignee_phone} not found."
                assignee_id = user["id"]

            # Create the chore
            await chore_service.create_chore(
                title=params.title,
                description=params.description,
                recurrence=params.recurrence,
                assigned_to=assignee_id,
            )

            assignee_msg = f"assigned to {params.assignee_phone}" if assignee_id else "unassigned"
            return f"Created chore '{params.title}' - {params.recurrence}, {assignee_msg}."

    except ValueError as e:
        logger.warning("Chore creation failed", error=str(e))
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_define_chore", error=str(e))
        return "Error: Unable to create chore. Please try again."


async def tool_log_chore(ctx: RunContext[Deps], params: LogChore) -> str:
    """
    Log a chore completion and request verification.

    Supports fuzzy matching for chore titles and Robin Hood swaps.
    Checks for name collisions with personal chores.

    Args:
        ctx: Agent runtime context with dependencies
        params: Chore logging parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_log_chore", title=params.chore_title_fuzzy, is_swap=params.is_swap):
            # Get all household chores to fuzzy match
            all_chores = await chore_service.get_chores()

            # Fuzzy match the household chore
            household_match = _fuzzy_match_chore(all_chores, params.chore_title_fuzzy)

            # Get user's personal chores to check for collision
            personal_chores = await personal_chore_service.get_personal_chores(
                owner_phone=ctx.deps.user_phone,
                status="ACTIVE",
            )
            personal_match = personal_chore_service.fuzzy_match_personal_chore(
                personal_chores, params.chore_title_fuzzy
            )

            # Check for collision
            if household_match and personal_match:
                # Cannot disambiguate - require more specific input
                return (
                    f"I found both a household chore '{household_match['title']}' and "
                    f"your personal chore '{personal_match['title']}'. "
                    f"Please be more specific: use '/personal done {params.chore_title_fuzzy}' "
                    f"for personal chores or provide the full household chore name."
                )

            # No collision - proceed with household chore logging
            if not household_match:
                return f"Error: No household chore found matching '{params.chore_title_fuzzy}'."

            chore_id = household_match["id"]
            chore_title = household_match["title"]

            # Check if chore is in TODO state
            if household_match["current_state"] != ChoreState.TODO:
                return (
                    f"Error: Chore '{chore_title}' is in state '{household_match['current_state']}' "
                    f"and cannot be logged right now."
                )

            # Log the completion
            await verification_service.request_verification(
                chore_id=chore_id,
                claimer_user_id=ctx.deps.user_id,
                notes=params.notes or "",
            )

            swap_msg = " (Robin Hood swap)" if params.is_swap else ""
            return (
                f"Logged completion of '{chore_title}'{swap_msg}. Awaiting verification from another household member."
            )

    except ValueError as e:
        logger.warning("Chore logging failed", error=str(e))
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_log_chore", error=str(e))
        return "Error: Unable to log chore. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register chore tools with the agent."""
    agent.tool(tool_define_chore)
    agent.tool(tool_log_chore)
