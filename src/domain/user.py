"""User domain models and enums."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


# Constants for validation
MAX_NAME_LENGTH = 50


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

    @field_validator("name")
    @classmethod
    def validate_name_usable(cls, v: str) -> str:
        """Validate name is usable - allows Unicode letters, spaces, hyphens, apostrophes."""
        v = v.strip()

        if not v or len(v) < 1:
            raise ValueError("Name cannot be empty")

        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Name too long (max {MAX_NAME_LENGTH} characters)")

        # Unicode letters, spaces, hyphens, apostrophes
        if not re.match(r"^[\w\s'-]+$", v, re.UNICODE):
            raise ValueError("Name can only contain letters, spaces, hyphens, and apostrophes")

        return v
