"""Error classification utilities for agent execution errors."""

from enum import Enum


class ErrorCategory(Enum):
    """Categories of errors that can occur during agent execution."""

    SERVICE_QUOTA_EXCEEDED = "service_quota_exceeded"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    AUTHENTICATION_FAILED = "authentication_failed"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


def classify_agent_error(exception: Exception) -> tuple[ErrorCategory, str]:
    """Classify an agent execution error and return a user-friendly message.

    Inspects the exception type, status codes, and error messages to determine
    the category of error and generate an appropriate user-facing message.

    Args:
        exception: The exception raised during agent execution

    Returns:
        Tuple of (ErrorCategory, user_friendly_message)
    """
    error_str = str(exception).lower()
    exception_type = type(exception).__name__

    # Check for quota/credit exceeded errors
    if any(
        phrase in error_str
        for phrase in [
            "quota exceeded",
            "insufficient credits",
            "credit limit",
            "credits exhausted",
            "out of credits",
        ]
    ):
        return (
            ErrorCategory.SERVICE_QUOTA_EXCEEDED,
            "The AI service quota has been exceeded. Please try again later or contact support.",
        )

    # Check for rate limit errors
    if any(
        phrase in error_str
        for phrase in [
            "rate limit",
            "too many requests",
            "rate_limit_exceeded",
            "throttled",
        ]
    ):
        return (
            ErrorCategory.RATE_LIMIT_EXCEEDED,
            "Too many requests. Please wait a moment and try again.",
        )

    # Check for authentication errors
    if any(
        phrase in error_str
        for phrase in [
            "authentication failed",
            "invalid api key",
            "unauthorized",
            "invalid token",
            "api key",
            "401",
        ]
    ) or exception_type in ["AuthenticationError", "PermissionError"]:
        return (
            ErrorCategory.AUTHENTICATION_FAILED,
            "Service authentication failed. Please contact support.",
        )

    # Check for network errors
    if any(
        phrase in error_str
        for phrase in [
            "connection",
            "timeout",
            "network",
            "503",
            "502",
            "504",
            "unreachable",
        ]
    ) or exception_type in ["ConnectionError", "TimeoutError"]:
        return (
            ErrorCategory.NETWORK_ERROR,
            "Network error occurred. Please check your connection and try again.",
        )

    # Default to unknown error
    return (
        ErrorCategory.UNKNOWN,
        "An unexpected error occurred. Please try again later.",
    )
