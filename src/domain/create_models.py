"""Pydantic models for creating records in database."""

import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from src.domain.user import UserRole, UserStatus


class UserCreate(BaseModel):
    """Pydantic model for creating a user record."""

    phone: str = Field(..., description="Phone number in E.164 format")
    name: str = Field(..., description="Display name of the user")
    email: str = Field(..., description="Email address (generated from phone for auth)")
    role: UserRole = Field(default=UserRole.MEMBER, description="User role in household")
    status: UserStatus = Field(default=UserStatus.PENDING, description="User account status")
    password: str = Field(..., description="User password")
    passwordConfirm: str = Field(..., description="Password confirmation")  # noqa: N815

    @field_validator("phone")
    @classmethod
    def validate_phone_e164(cls, v: str) -> str:
        """Validate phone number is in E.164 format."""
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            msg = "Phone number must be in E.164 format (e.g., +14155552671)"
            raise ValueError(msg)
        return v


class InviteCreate(BaseModel):
    """Pydantic model for creating a pending invite record."""

    phone: str = Field(..., description="Phone number in E.164 format")
    invited_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        description="Invite timestamp",
    )
    invite_message_id: str | None = Field(None, description="WhatsApp message ID")

    @field_validator("phone")
    @classmethod
    def validate_phone_e164(cls, v: str) -> str:
        """Validate phone number is in E.164 format."""
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            msg = "Phone number must be in E.164 format (e.g., +14155552671)"
            raise ValueError(msg)
        return v


class HouseConfigCreate(BaseModel):
    """Pydantic model for creating a house config record."""

    name: str = Field(..., description="House name")
    code: str = Field(..., description="House code")
    password: str | None = Field(None, description="House password")

    @field_validator("code")
    @classmethod
    def validate_code_length(cls, v: str) -> str:
        """Validate code is at least 4 characters."""
        if len(v) < 4:  # noqa: PLR2004
            msg = "Code must be at least 4 characters"
            raise ValueError(msg)
        return v

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v: str | None) -> str | None:
        """Validate password is at least 8 characters if provided."""
        if v is not None and len(v) < 8:  # noqa: PLR2004
            msg = "Password must be at least 8 characters"
            raise ValueError(msg)
        return v
