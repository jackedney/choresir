"""Analytics tools for the choresir agent."""

import logging
from datetime import UTC, datetime
from typing import Literal

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.core.config import Constants
from src.models.service_models import CompletionRate, LeaderboardEntry, OverdueChore, UserStatistics
from src.services import analytics_service


logger = logging.getLogger(__name__)

# Title threshold constants for user stats
TITLE_THRESHOLD_MACHINE = 10
TITLE_THRESHOLD_CONTRIBUTOR = 5
TITLE_THRESHOLD_STARTER = 1

# Period constants for analytics
PERIOD_WEEKLY_DAYS = 7
PERIOD_MONTHLY_DAYS = 30


class GetAnalytics(BaseModel):
    """Parameters for getting analytics."""

    metric: Literal["leaderboard", "completion_rate", "overdue"] = Field(
        description="Type of analytics metric to retrieve"
    )
    period_days: int = Field(default=30, description="Number of days to look back (default: 30)")


def _format_leaderboard(leaderboard: list[LeaderboardEntry], period_days: int) -> str:
    """
    Format leaderboard for WhatsApp display.

    Args:
        leaderboard: List of leaderboard entries
        period_days: Period in days

    Returns:
        Formatted leaderboard message
    """
    if not leaderboard:
        return f"No completions in the last {period_days} days."

    # Show top 3 (or fewer if less than 3 users)
    top_n = min(3, len(leaderboard))
    lines = [f"🏆 Top {top_n} ({period_days} days):"]

    for i, entry in enumerate(leaderboard[:top_n], 1):
        name = entry.user_name
        count = entry.completion_count
        lines.append(f"{i}. {name} ({count})")

    return "\n".join(lines)


def _format_completion_rate(stats: CompletionRate) -> str:
    """
    Format completion rate for WhatsApp display.

    Args:
        stats: Completion rate statistics

    Returns:
        Formatted completion rate message
    """
    total = stats.total_completions
    period = stats.period_days

    if total == 0:
        return f"No completions in the last {period} days."

    on_time_pct = stats.on_time_percentage
    overdue_pct = stats.overdue_percentage

    return (
        f"📊 Completion Rate ({period} days):\nTotal: {total} chores\nOn-time: {on_time_pct}%\nOverdue: {overdue_pct}%"
    )


def _format_overdue_chores(chores: list[OverdueChore]) -> str:
    """
    Format overdue chores for WhatsApp display.

    Args:
        chores: List of overdue chore records

    Returns:
        Formatted overdue chores message
    """
    if not chores:
        return "✅ No overdue chores!"

    now = datetime.now(UTC)
    lines = [f"⚠️ {len(chores)} overdue chore(s):"]

    for chore in chores[: Constants.WHATSAPP_OVERDUE_CHORES_DISPLAY_LIMIT]:
        title = chore.title
        deadline = datetime.fromisoformat(chore.deadline)
        # If deadline is naive (no timezone), assume UTC
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        days_overdue = (now - deadline).days

        if days_overdue == 0:
            time_str = "today"
        elif days_overdue == 1:
            time_str = "1 day"
        else:
            time_str = f"{days_overdue} days"

        lines.append(f"• '{title}' ({time_str})")

    max_display = Constants.WHATSAPP_OVERDUE_CHORES_DISPLAY_LIMIT
    if len(chores) > max_display:
        lines.append(f"... and {len(chores) - max_display} more")

    return "\n".join(lines)


async def tool_get_analytics(_ctx: RunContext[Deps], params: GetAnalytics) -> str:
    """
    Get household analytics and metrics.

    Supports leaderboards, completion rates, and overdue chores.

    Args:
        ctx: Agent runtime context with dependencies
        params: Analytics query parameters

    Returns:
        Formatted analytics message
    """
    try:
        with logfire.span("tool_get_analytics", metric=params.metric, period=params.period_days):
            if params.metric == "leaderboard":
                leaderboard = await analytics_service.get_leaderboard(period_days=params.period_days)
                return _format_leaderboard(leaderboard, params.period_days)

            if params.metric == "completion_rate":
                stats = await analytics_service.get_completion_rate(period_days=params.period_days)
                return _format_completion_rate(stats)

            if params.metric == "overdue":
                chores = await analytics_service.get_overdue_chores()
                return _format_overdue_chores(chores)

            return f"Error: Unknown metric '{params.metric}'."

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Unexpected error in tool_get_analytics", extra={"error": str(e)})
        return "Error: Unable to retrieve analytics. Please try again."


class GetStats(BaseModel):
    """Parameters for getting user statistics."""

    period_days: int = Field(
        default=7,
        description="Number of days to look back for statistics (default: 7 for weekly)",
    )


def _format_user_stats(stats: UserStatistics, period_days: int) -> str:
    """Format user statistics for WhatsApp display.

    Args:
        stats: User statistics dictionary
        period_days: Period in days for context

    Returns:
        Formatted stats message
    """
    rank_str = f"#{stats.rank}" if stats.rank is not None else "Not ranked yet"
    completions = stats.completions
    pending = stats.claims_pending
    overdue = stats.overdue_chores

    # Build dynamic title based on performance
    match completions:
        case c if c >= TITLE_THRESHOLD_MACHINE:
            title = "🏆 The Machine"
        case c if c >= TITLE_THRESHOLD_CONTRIBUTOR:
            title = "💪 Solid Contributor"
        case c if c >= TITLE_THRESHOLD_STARTER:
            title = "👍 Getting Started"
        case _:
            title = "😴 The Observer"

    if period_days == PERIOD_WEEKLY_DAYS:
        period_label = "This Week"
    elif period_days == PERIOD_MONTHLY_DAYS:
        period_label = "This Month"
    else:
        period_label = f"Last {period_days} Days"

    lines = [
        f"📊 *Your Stats ({period_label})*",
        "",
        f"*{title}*",
        "",
        f"Rank: {rank_str}",
        f"Chores Completed: {completions}",
        f"Pending Verification: {pending}",
        f"Overdue: {overdue}",
    ]

    # Add encouragement/warning based on status
    if overdue and overdue > 0:
        lines.append("")
        lines.append(f"⚠️ You have {overdue} overdue chore(s)!")
    elif completions == 0:
        lines.append("")
        lines.append("💡 Complete a chore to get on the board!")

    return "\n".join(lines)


async def tool_get_stats(ctx: RunContext[Deps], params: GetStats) -> str:
    """Get your personal chore statistics and leaderboard ranking.

    Use this when the user asks for their stats, score, ranking, or standing.
    Common triggers: "stats", "my stats", "score", "how am I doing", "leaderboard".

    Args:
        ctx: Agent runtime context with dependencies
        params: Stats query parameters

    Returns:
        Formatted personal statistics message
    """
    try:
        with logfire.span("tool_get_stats", user_id=ctx.deps.user_id, period=params.period_days):
            # Get user statistics from analytics service
            stats = await analytics_service.get_user_statistics(
                user_id=ctx.deps.user_id,
                period_days=params.period_days,
            )

            return _format_user_stats(stats, params.period_days)

    except (RuntimeError, KeyError, ConnectionError) as e:
        logger.error("Unexpected error in tool_get_stats", extra={"error": str(e)})
        return "Error: Unable to retrieve your stats. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent."""
    agent.tool(tool_get_analytics)
    agent.tool(tool_get_stats)
