"""Agent tools for personal chore management."""

import logging

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.core import db_client
from src.core.recurrence_parser import cron_to_human
from src.domain.user import UserStatus
from src.services import personal_chore_service, personal_verification_service, user_service


logger = logging.getLogger(__name__)


class CreatePersonalChore(BaseModel):
    """Parameters for creating a personal chore."""

    title: str = Field(description="Personal chore title (e.g., 'Go to gym')")
    recurrence: str | None = Field(
        default=None,
        description=(
            "Recurrence pattern: CRON format, 'every X days', 'every morning', "
            "'every friday', or 'by friday' for one-time tasks"
        ),
    )
    accountability_partner_name: str | None = Field(
        default=None,
        description="Name of household member to be accountability partner (optional)",
    )


class LogPersonalChore(BaseModel):
    """Parameters for logging personal chore completion."""

    chore_title_fuzzy: str = Field(description="Personal chore title or partial match (fuzzy search)")
    notes: str | None = Field(default=None, description="Optional notes about completion")


class VerifyPersonalChore(BaseModel):
    """Parameters for verifying someone's personal chore."""

    log_id: str = Field(description="Personal chore log ID to verify")
    approved: bool = Field(description="True to approve, False to reject")
    feedback: str | None = Field(default=None, description="Optional feedback message")


class GetPersonalStats(BaseModel):
    """Parameters for getting personal chore statistics."""

    period_days: int = Field(default=30, description="Number of days to include in stats")


class ListPersonalChores(BaseModel):
    """Parameters for listing personal chores."""

    filter_type: str = Field(
        default="all",
        description="Filter: 'all', 'pending', or 'overdue'",
    )


class RemovePersonalChore(BaseModel):
    """Parameters for removing a personal chore."""

    chore_title_fuzzy: str = Field(description="Personal chore title or partial match to remove")


async def tool_create_personal_chore(ctx: RunContext[Deps], params: CreatePersonalChore) -> str:
    """Create a new personal chore.

    Args:
        ctx: Agent runtime context with dependencies
        params: Personal chore creation parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_create_personal_chore", title=params.title):
            # Resolve accountability partner if provided
            partner_phone = None
            if params.accountability_partner_name:
                # Search for user by name
                all_users = await db_client.list_records(
                    collection="members",
                    filter_query=f'status = "{UserStatus.ACTIVE}"',
                    sort="+name",
                )
                partner = None

                # Case-insensitive name match
                name_lower = params.accountability_partner_name.lower()
                for user in all_users:
                    if user["name"].lower() == name_lower:
                        partner = user
                        break

                if not partner:
                    return f"Error: User '{params.accountability_partner_name}' not found in household."

                # Prevent self-assignment
                if partner["phone"] == ctx.deps.user_phone:
                    return "Error: You cannot be your own accountability partner."

                partner_phone = partner["phone"]

            # Create the personal chore
            await personal_chore_service.create_personal_chore(
                owner_phone=ctx.deps.user_phone,
                title=params.title,
                recurrence=params.recurrence,
                accountability_partner_phone=partner_phone,
            )

            # Build response message
            recurrence_msg = f"({params.recurrence})" if params.recurrence else "(one-time task)"

            if partner_phone:
                partner_msg = f" {params.accountability_partner_name} will verify your completions."
            else:
                partner_msg = " Self-verified."

            return f"✅ Created personal chore '{params.title}' {recurrence_msg}.{partner_msg}"

    except ValueError as e:
        logger.warning("Personal chore creation failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_create_personal_chore", extra={"error": str(e)})
        return "Error: Unable to create personal chore. Please try again."


async def tool_log_personal_chore(ctx: RunContext[Deps], params: LogPersonalChore) -> str:
    """Log completion of a personal chore.

    Args:
        ctx: Agent runtime context with dependencies
        params: Personal chore logging parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_log_personal_chore", title=params.chore_title_fuzzy):
            # Get user's personal chores
            all_chores = await personal_chore_service.get_personal_chores(
                owner_phone=ctx.deps.user_phone,
                status="ACTIVE",
            )

            # Fuzzy match the chore
            matched_chore = personal_chore_service.fuzzy_match_personal_chore(all_chores, params.chore_title_fuzzy)

            if not matched_chore:
                return f"Error: No personal chore found matching '{params.chore_title_fuzzy}'."

            # Log the completion
            log = await personal_verification_service.log_personal_chore(
                chore_id=matched_chore["id"],
                owner_phone=ctx.deps.user_phone,
                notes=params.notes or "",
            )

            # Build response based on verification status
            if log.verification_status == "SELF_VERIFIED":
                return f"✅ Logged '{matched_chore['title']}'. Nice work!"
            # Pending partner verification
            partner_phone = log.accountability_partner_phone
            partner_user = await user_service.get_user_by_phone(phone=partner_phone)
            partner_name = partner_user["name"] if partner_user else "your partner"

            return f"✅ Logged '{matched_chore['title']}'. Awaiting verification from {partner_name}."

    except ValueError as e:
        logger.warning("Personal chore logging failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_log_personal_chore", extra={"error": str(e)})
        return "Error: Unable to log personal chore. Please try again."


async def tool_verify_personal_chore(ctx: RunContext[Deps], params: VerifyPersonalChore) -> str:
    """Verify or reject someone's personal chore completion.

    Args:
        ctx: Agent runtime context with dependencies
        params: Verification parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_verify_personal_chore", log_id=params.log_id):
            # Perform verification
            updated_log = await personal_verification_service.verify_personal_chore(
                log_id=params.log_id,
                verifier_phone=ctx.deps.user_phone,
                approved=params.approved,
                feedback=params.feedback or "",
            )

            # Get chore details for response
            chore = await personal_chore_service.get_personal_chore_by_id(
                chore_id=updated_log.personal_chore_id,
                owner_phone=updated_log.owner_phone,
            )

            # Get owner name
            owner = await user_service.get_user_by_phone(phone=updated_log.owner_phone)
            owner_name = owner["name"] if owner else "the user"

            if params.approved:
                return f"✅ Verified {owner_name}'s '{chore['title']}'. Keep it up!"
            return f"❌ Rejected {owner_name}'s '{chore['title']}'."

    except PermissionError as e:
        logger.warning("Verification permission denied", extra={"error": str(e)})
        return f"Error: {e!s}"
    except ValueError as e:
        logger.warning("Verification failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_verify_personal_chore", extra={"error": str(e)})
        return "Error: Unable to verify personal chore. Please try again."


async def tool_get_personal_stats(ctx: RunContext[Deps], params: GetPersonalStats) -> str:
    """Get personal chore statistics.

    Args:
        ctx: Agent runtime context with dependencies
        params: Stats parameters

    Returns:
        Formatted stats message
    """
    try:
        with logfire.span("tool_get_personal_stats"):
            stats = await personal_verification_service.get_personal_stats(
                owner_phone=ctx.deps.user_phone,
                period_days=params.period_days,
            )

            week_days = 7
            period_label = "This Week" if params.period_days == week_days else f"Last {params.period_days} Days"

            return (
                f"📊 Your Personal Stats ({period_label})\n\n"
                f"Active Chores: {stats.total_chores}\n"
                f"Completions: {stats.completions_this_period}\n"
                f"Pending Verification: {stats.pending_verifications}\n"
                f"Completion Rate: {stats.completion_rate}%"
            )

    except Exception as e:
        logger.error("Unexpected error in tool_get_personal_stats", extra={"error": str(e)})
        return "Error: Unable to retrieve personal stats. Please try again."


async def tool_list_personal_chores(ctx: RunContext[Deps], _params: ListPersonalChores) -> str:
    """List personal chores."""
    try:
        with logfire.span("tool_list_personal_chores"):
            chores = await personal_chore_service.get_personal_chores(
                owner_phone=ctx.deps.user_phone,
                status="ACTIVE",
            )

            if not chores:
                return "You have no personal chores. Use '/personal add [task]' to create one."

            # Format chore list
            lines = ["Your Personal Chores:\n"]
            for chore in chores:
                title = chore["title"]
                recurrence = chore.get("recurrence", "")
                if recurrence:
                    schedule_human = cron_to_human(recurrence)
                    lines.append(f"- {title} ({schedule_human})")
                else:
                    lines.append(f"- {title} (one-time)")

            return "\n".join(lines)

    except Exception as e:
        logger.error("Unexpected error in tool_list_personal_chores", extra={"error": str(e)})
        return "Error: Unable to list personal chores. Please try again."


async def tool_remove_personal_chore(ctx: RunContext[Deps], params: RemovePersonalChore) -> str:
    """Remove (archive) a personal chore.

    Args:
        ctx: Agent runtime context with dependencies
        params: Removal parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_remove_personal_chore", title=params.chore_title_fuzzy):
            # Get user's personal chores
            all_chores = await personal_chore_service.get_personal_chores(
                owner_phone=ctx.deps.user_phone,
                status="ACTIVE",
            )

            # Fuzzy match the chore
            matched_chore = personal_chore_service.fuzzy_match_personal_chore(all_chores, params.chore_title_fuzzy)

            if not matched_chore:
                return f"Error: No personal chore found matching '{params.chore_title_fuzzy}'."

            # Archive the chore
            await personal_chore_service.delete_personal_chore(
                chore_id=matched_chore["id"],
                owner_phone=ctx.deps.user_phone,
            )

            return f"✅ Removed personal chore '{matched_chore['title']}'."

    except Exception as e:
        logger.error("Unexpected error in tool_remove_personal_chore", extra={"error": str(e)})
        return "Error: Unable to remove personal chore. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register personal chore tools with the agent."""

    agent.tool(tool_create_personal_chore)
    agent.tool(tool_log_personal_chore)
    agent.tool(tool_verify_personal_chore)
    agent.tool(tool_get_personal_stats)
    agent.tool(tool_list_personal_chores)
    agent.tool(tool_remove_personal_chore)
