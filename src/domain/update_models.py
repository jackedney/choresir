"""Update models for database operations."""

from pydantic import BaseModel


class MemberUpdate(BaseModel):
    """Update payload for member name and role."""

    name: str
    role: str


class MemberStatusUpdate(BaseModel):
    """Update payload for member status."""

    status: str


class UserStatusUpdate(BaseModel):
    """DTO for updating user status."""

    status: str
