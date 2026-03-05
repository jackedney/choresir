"""Exception hierarchy for Choresir domain errors."""

from __future__ import annotations


class ChoresirError(Exception):
    """Base for all domain errors."""


class InvalidTransitionError(ChoresirError):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from {current} to {target}")


class NotFoundError(ChoresirError):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity: str, identifier: str | int) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier}")


class AuthorizationError(ChoresirError):
    """Member lacks permission for the operation."""


class RateLimitExceededError(ChoresirError):
    """Per-user or global rate limit hit."""


class WebhookAuthError(ChoresirError):
    """Invalid webhook signature."""
