"""Log domain models for audit trail."""

from enum import StrEnum

from pydantic import BaseModel, Field


class VerificationStatus(StrEnum):
    """Verification status for task completion."""

    SELF_VERIFIED = "SELF_VERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class TaskLog(BaseModel):
    """Task log entry data transfer object for audit trail."""

    id: str = Field(..., description="Unique log ID from database")
    created: str = Field(..., description="Creation timestamp (ISO format)")
    updated: str = Field(..., description="Last update timestamp (ISO format)")
    task_id: str = Field(..., description="ID of task this log relates to")
    user_id: str = Field(..., description="ID of user who performed the action")
    action: str = Field(
        ...,
        description="Action performed (e.g., 'completed', 'verified', 'rejected')",
    )
    notes: str | None = Field(default=None, description="Additional notes about the action")
    timestamp: str | None = Field(default=None, description="When the action occurred (ISO format)")
    verification_status: VerificationStatus | None = Field(
        default=None,
        description="Verification status for completion actions",
    )
    verifier_id: str | None = Field(default=None, description="ID of user who verified completion")
    verifier_feedback: str | None = Field(default=None, description="Feedback from verifier if rejected")
    original_assignee_id: str | None = Field(
        default=None,
        description="Original assignee ID if task was swapped",
    )
    actual_completer_id: str | None = Field(
        default=None,
        description="ID of user who actually completed the task",
    )
    is_swap: bool = Field(default=False, description="Whether this was a swap completion")
