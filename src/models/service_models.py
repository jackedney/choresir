"""Pydantic models for service layer return types.

These models provide type safety at service boundaries, converting database
dictionaries into typed objects with validation.
"""

from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    """User entry in completion leaderboard."""

    user_id: str
    user_name: str
    completion_count: int


class CompletionRate(BaseModel):
    """Completion rate statistics for a period."""

    total_completions: int
    on_time: int
    overdue: int
    on_time_percentage: float
    overdue_percentage: float
    period_days: int


class OverdueChore(BaseModel):
    """Overdue chore record from database."""

    id: str
    title: str
    current_state: str
    assigned_to: str | None = None
    deadline: str
    created: str
    updated: str


class UserStatistics(BaseModel):
    """Comprehensive statistics for a user."""

    user_id: str
    user_name: str
    completions: int
    claims_pending: int | None
    claims_pending_error: str | None = None
    overdue_chores: int | None
    overdue_chores_error: str | None = None
    rank: int | None
    rank_error: str | None = None
    period_days: int


class HouseholdSummary(BaseModel):
    """Overall household statistics."""

    active_members: int
    completions_this_period: int
    overdue_chores: int
    pending_verifications: int
    period_days: int


class NotificationResult(BaseModel):
    """Result of sending a notification."""

    user_id: str
    phone: str
    success: bool
    error: str | None = None


class PersonalChoreLog(BaseModel):
    """Personal chore completion log record."""

    id: str
    personal_chore_id: str
    owner_phone: str
    completed_at: str
    verification_status: str
    accountability_partner_phone: str
    partner_feedback: str
    notes: str
    created: str
    updated: str
    # Optional enriched fields (added by service layer)
    chore_title: str | None = None
    owner_phone_display: str | None = None


class PersonalChoreStatistics(BaseModel):
    """Personal chore statistics for a user."""

    total_chores: int
    completions_this_period: int
    pending_verifications: int
    completion_rate: float
    period_days: int
