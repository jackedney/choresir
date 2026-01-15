"""User domain models and enums."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class UserRole(StrEnum):
    """User role in the household."""

    ADMIN = "admin"
    MEMBER = "member"


class UserStatus(StrEnum):
    """User account status."""

    PENDING = "pending"
    ACTIVE = "active"
    BANNED = "banned"


class User(BaseModel):
    """User data transfer object."""

    id: str = Field(..., description="Unique user ID from PocketBase")
    phone: str = Field(..., description="Phone number in E.164 format (e.g., +14155552671)")
    name: str = Field(..., description="Display name of the user")
    role: UserRole = Field(default=UserRole.MEMBER, description="User role in household")
    status: UserStatus = Field(default=UserStatus.PENDING, description="User account status")

    @field_validator("phone")
    @classmethod
    def validate_phone_e164(cls, v: str) -> str:
        """Validate phone number is in E.164 format."""
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            msg = "Phone number must be in E.164 format (e.g., +14155552671)"
            raise ValueError(msg)
        return v
