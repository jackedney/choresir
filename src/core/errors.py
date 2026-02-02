"""Error classification utilities for agent execution errors."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ErrorCategory(Enum):
    """Categories of errors that can occur during agent execution."""

    SERVICE_QUOTA_EXCEEDED = "service_quota_exceeded"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    AUTHENTICATION_FAILED = "authentication_failed"
    NETWORK_ERROR = "network_error"
    CHORE_ALREADY_CLAIMED = "chore_already_claimed"
    INVALID_CHORE_ID = "invalid_chore_id"
    PERMISSION_DENIED = "permission_denied"
    INVALID_RECURRENCE_PATTERN = "invalid_recurrence_pattern"
    USER_NOT_FOUND = "user_not_found"
    INVALID_STATE_TRANSITION = "invalid_state_transition"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCode:
    """Error codes for specific error conditions."""

    # Service errors
    ERR_SERVICE_QUOTA_EXCEEDED = "ERR_SERVICE_QUOTA_EXCEEDED"
    ERR_RATE_LIMIT_EXCEEDED = "ERR_RATE_LIMIT_EXCEEDED"
    ERR_AUTHENTICATION_FAILED = "ERR_AUTHENTICATION_FAILED"
    ERR_NETWORK_ERROR = "ERR_NETWORK_ERROR"

    # Chore errors
    ERR_CHORE_ALREADY_CLAIMED = "ERR_CHORE_ALREADY_CLAIMED"
    ERR_INVALID_CHORE_ID = "ERR_INVALID_CHORE_ID"
    ERR_INVALID_STATE_TRANSITION = "ERR_INVALID_STATE_TRANSITION"
    ERR_INVALID_RECURRENCE_PATTERN = "ERR_INVALID_RECURRENCE_PATTERN"

    # Permission errors
    ERR_PERMISSION_DENIED = "ERR_PERMISSION_DENIED"

    # User errors
    ERR_USER_NOT_FOUND = "ERR_USER_NOT_FOUND"
    ERR_USER_ALREADY_EXISTS = "ERR_USER_ALREADY_EXISTS"
    ERR_USER_NOT_APPROVED = "ERR_USER_NOT_APPROVED"

    # Generic errors
    ERR_UNKNOWN = "ERR_UNKNOWN"


class ErrorResponse(BaseModel):
    """Structured error response with user-friendly messaging."""

    code: str
    message: str
    suggestion: str
    severity: ErrorSeverity


_ERROR_PATTERNS: dict[
    Literal["quota", "rate_limit", "auth", "network", "validation", "context_length"],
    dict[str, list[str] | set[str]],
] = {
    "quota": {
        "phrases": [
            "quota exceeded",
            "insufficient credits",
            "credit limit",
            "credits exhausted",
            "out of credits",
        ],
        "exception_types": set(),
    },
    "rate_limit": {
        "phrases": [
            "rate limit",
            "too many requests",
            "rate_limit_exceeded",
            "throttled",
        ],
        "exception_types": set(),
    },
    "auth": {
        "phrases": [
            "authentication failed",
            "invalid api key",
            "unauthorized",
            "invalid token",
            "api key",
            "401",
        ],
        "exception_types": {"AuthenticationError", "PermissionError"},
    },
    "network": {
        "phrases": [
            "connection",
            "timeout",
            "network",
            "503",
            "502",
            "504",
            "unreachable",
        ],
        "exception_types": {"ConnectionError", "TimeoutError"},
    },
    "validation": {"phrases": [], "exception_types": set()},
    "context_length": {"phrases": [], "exception_types": set()},
}


def _match_error_pattern(
    *,
    error_str: str,
    exception_type: str,
    pattern_type: Literal["quota", "rate_limit", "auth", "network", "validation", "context_length"],
) -> bool:
    """Return True if the error matches the configured pattern type."""
    patterns = _ERROR_PATTERNS[pattern_type]
    return any(phrase in error_str for phrase in patterns["phrases"]) or exception_type in patterns["exception_types"]


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

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="quota"):
        return (
            ErrorCategory.SERVICE_QUOTA_EXCEEDED,
            "The AI service quota has been exceeded. Please try again later or contact support.",
        )

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="rate_limit"):
        return (
            ErrorCategory.RATE_LIMIT_EXCEEDED,
            "Too many requests. Please wait a moment and try again.",
        )

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="auth"):
        return (
            ErrorCategory.AUTHENTICATION_FAILED,
            "Service authentication failed. Please contact support.",
        )

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="network"):
        return (
            ErrorCategory.NETWORK_ERROR,
            "Network error occurred. Please check your connection and try again.",
        )

    return (
        ErrorCategory.UNKNOWN,
        "An unexpected error occurred. Please try again later.",
    )


def classify_error_with_response(exception: Exception) -> ErrorResponse:  # noqa: C901, PLR0911
    """Classify an error and return a structured response with recovery suggestions.

    Args:
        exception: The exception raised during execution

    Returns:
        ErrorResponse with code, message, suggestion, and severity
    """
    error_str = str(exception).lower()
    exception_type = type(exception).__name__

    if "already claimed" in error_str or "cannot claim" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_CHORE_ALREADY_CLAIMED,
            message="This chore has already been claimed by someone else.",
            suggestion="Try `/list chores` to see available chores.",
            severity=ErrorSeverity.LOW,
        )

    if "chore not found" in error_str or "could not find chore" in error_str or "invalid chore" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_CHORE_ID,
            message="I couldn't find that chore.",
            suggestion="Use `/list chores` to see current chores.",
            severity=ErrorSeverity.LOW,
        )

    if exception_type == "PermissionError" or "permission denied" in error_str or "does not belong to" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_PERMISSION_DENIED,
            message="You don't have permission for this action.",
            suggestion="Contact your household admin if you think this is an error.",
            severity=ErrorSeverity.MEDIUM,
        )

    if exception_type == "KeyError" and ("user" in error_str or "not found" in error_str):
        return ErrorResponse(
            code=ErrorCode.ERR_USER_NOT_FOUND,
            message="User not found.",
            suggestion="Make sure you're registered. Try `/help` for more information.",
            severity=ErrorSeverity.MEDIUM,
        )

    if exception_type == "ValueError" and ("cannot" in error_str or "invalid state" in error_str):
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_STATE_TRANSITION,
            message="This action cannot be performed in the current state.",
            suggestion="Check the chore status with `/list chores` and try again.",
            severity=ErrorSeverity.LOW,
        )

    if "recurrence" in error_str or "pattern" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_RECURRENCE_PATTERN,
            message="Invalid recurrence pattern.",
            suggestion="Use formats like 'daily', 'weekly', 'every 3 days', or 'Mon,Wed,Fri'.",
            severity=ErrorSeverity.LOW,
        )

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="quota"):
        return ErrorResponse(
            code=ErrorCode.ERR_SERVICE_QUOTA_EXCEEDED,
            message="The AI service quota has been exceeded.",
            suggestion="Please try again later or contact support.",
            severity=ErrorSeverity.HIGH,
        )

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="rate_limit"):
        return ErrorResponse(
            code=ErrorCode.ERR_RATE_LIMIT_EXCEEDED,
            message="Too many requests.",
            suggestion="Please wait a moment and try again.",
            severity=ErrorSeverity.MEDIUM,
        )

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="auth"):
        return ErrorResponse(
            code=ErrorCode.ERR_AUTHENTICATION_FAILED,
            message="Service authentication failed.",
            suggestion="Please contact support.",
            severity=ErrorSeverity.CRITICAL,
        )

    if _match_error_pattern(error_str=error_str, exception_type=exception_type, pattern_type="network"):
        return ErrorResponse(
            code=ErrorCode.ERR_NETWORK_ERROR,
            message="Network error occurred.",
            suggestion="Please check your connection and try again.",
            severity=ErrorSeverity.MEDIUM,
        )

    return ErrorResponse(
        code=ErrorCode.ERR_UNKNOWN,
        message="An unexpected error occurred.",
        suggestion="Please try again later. If the problem persists, contact support.",
        severity=ErrorSeverity.MEDIUM,
    )
