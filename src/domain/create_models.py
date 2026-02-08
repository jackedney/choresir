"""Pydantic models for creating records in database."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.user import UserRole, UserStatus


class UserCreate(BaseModel):
    """Pydantic model for creating a user record."""

    model_config = ConfigDict(populate_by_name=True)

    phone: str = Field(..., description="Phone number in E.164 format")
    name: str = Field(..., description="Display name of the user")
    email: str = Field(..., description="Email address (generated from phone for auth)")
    role: UserRole = Field(default=UserRole.MEMBER, description="User role in household")
    status: UserStatus = Field(default=UserStatus.PENDING_NAME, description="User account status")
    password: str = Field(..., description="User password")
    password_confirm: str = Field(
        ...,
        validation_alias="passwordConfirm",
        serialization_alias="passwordConfirm",
        description="Password confirmation",
    )

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
