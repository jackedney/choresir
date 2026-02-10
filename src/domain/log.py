"""Log domain models for audit trail."""

from datetime import datetime

from pydantic import BaseModel, Field


class Log(BaseModel):
    """Log entry data transfer object for audit trail."""

    id: str = Field(..., description="Unique log ID from database")
    chore_id: str = Field(..., description="ID of chore this log relates to")
    user_id: str = Field(..., description="ID of user who performed the action")
    action: str = Field(
        ...,
        description="Action performed (e.g., 'completed', 'verified', 'rejected', 'voted_yes')",
    )
    timestamp: datetime = Field(default_factory=datetime.now, description="When the action occurred")
