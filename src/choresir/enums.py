"""All domain enums for Choresir."""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    """Lifecycle states for a task."""

    PENDING = "pending"
    CLAIMED = "claimed"
    VERIFIED = "verified"


class VerificationMode(StrEnum):
    """How a task completion is verified."""

    NONE = "none"
    PEER = "peer"
    PARTNER = "partner"


class MemberRole(StrEnum):
    """Role within the household."""

    ADMIN = "admin"
    MEMBER = "member"


class MemberStatus(StrEnum):
    """Onboarding state of a member."""

    PENDING = "pending"
    ACTIVE = "active"


class JobStatus(StrEnum):
    """Processing state of a queued message job."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class TaskVisibility(StrEnum):
    """Whether a task is shared or personal."""

    SHARED = "shared"
    PERSONAL = "personal"
