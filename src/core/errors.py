"""Error classification utilities for agent execution errors."""

from collections.abc import Callable
from enum import Enum

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


def _check_chore_claimed(error_str: str, _exception_type: str) -> ErrorResponse | None:
    """Check for chore already claimed errors."""
    if "already claimed" in error_str or "cannot claim" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_CHORE_ALREADY_CLAIMED,
            message="This chore has already been claimed by someone else.",
            suggestion="Try `/list chores` to see available chores.",
            severity=ErrorSeverity.LOW,
        )
    return None


def _check_invalid_chore(error_str: str, _exception_type: str) -> ErrorResponse | None:
    """Check for invalid chore ID errors."""
    if "chore not found" in error_str or "could not find chore" in error_str or "invalid chore" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_CHORE_ID,
            message="I couldn't find that chore.",
            suggestion="Use `/list chores` to see current chores.",
            severity=ErrorSeverity.LOW,
        )
    return None


def _check_permission_denied(error_str: str, exception_type: str) -> ErrorResponse | None:
    """Check for permission denied errors."""
    if exception_type == "PermissionError" or "permission denied" in error_str or "does not belong to" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_PERMISSION_DENIED,
            message="You don't have permission for this action.",
            suggestion="Contact your household admin if you think this is an error.",
            severity=ErrorSeverity.MEDIUM,
        )
    return None


def _check_user_not_found(error_str: str, exception_type: str) -> ErrorResponse | None:
    """Check for user not found errors."""
    if exception_type == "KeyError" and ("user" in error_str or "not found" in error_str):
        return ErrorResponse(
            code=ErrorCode.ERR_USER_NOT_FOUND,
            message="User not found.",
            suggestion="Make sure you're registered. Try `/help` for more information.",
            severity=ErrorSeverity.MEDIUM,
        )
    return None


def _check_invalid_state(error_str: str, exception_type: str) -> ErrorResponse | None:
    """Check for invalid state transition errors."""
    if exception_type == "ValueError" and ("cannot" in error_str or "invalid state" in error_str):
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_STATE_TRANSITION,
            message="This action cannot be performed in the current state.",
            suggestion="Check the chore status with `/list chores` and try again.",
            severity=ErrorSeverity.LOW,
        )
    return None


def _check_recurrence_pattern(error_str: str, _exception_type: str) -> ErrorResponse | None:
    """Check for invalid recurrence pattern errors."""
    if "recurrence" in error_str or "pattern" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_RECURRENCE_PATTERN,
            message="Invalid recurrence pattern.",
            suggestion="Use formats like 'daily', 'weekly', 'every 3 days', or 'Mon,Wed,Fri'.",
            severity=ErrorSeverity.LOW,
        )
    return None


def _check_quota_exceeded(error_str: str, _exception_type: str) -> ErrorResponse | None:
    """Check for quota/credit exceeded errors."""
    quota_phrases = [
        "quota exceeded",
        "insufficient credits",
        "credit limit",
        "credits exhausted",
        "out of credits",
    ]
    if any(phrase in error_str for phrase in quota_phrases):
        return ErrorResponse(
            code=ErrorCode.ERR_SERVICE_QUOTA_EXCEEDED,
            message="The AI service quota has been exceeded.",
            suggestion="Please try again later or contact support.",
            severity=ErrorSeverity.HIGH,
        )
    return None


def _check_rate_limit(error_str: str, _exception_type: str) -> ErrorResponse | None:
    """Check for rate limit errors."""
    rate_limit_phrases = [
        "rate limit",
        "too many requests",
        "rate_limit_exceeded",
        "throttled",
    ]
    if any(phrase in error_str for phrase in rate_limit_phrases):
        return ErrorResponse(
            code=ErrorCode.ERR_RATE_LIMIT_EXCEEDED,
            message="Too many requests.",
            suggestion="Please wait a moment and try again.",
            severity=ErrorSeverity.MEDIUM,
        )
    return None


def _check_authentication(error_str: str, exception_type: str) -> ErrorResponse | None:
    """Check for authentication errors."""
    auth_phrases = [
        "authentication failed",
        "invalid api key",
        "unauthorized",
        "invalid token",
        "api key",
        "401",
    ]
    if any(phrase in error_str for phrase in auth_phrases) or exception_type == "AuthenticationError":
        return ErrorResponse(
            code=ErrorCode.ERR_AUTHENTICATION_FAILED,
            message="Service authentication failed.",
            suggestion="Please contact support.",
            severity=ErrorSeverity.CRITICAL,
        )
    return None


def _check_network_error(error_str: str, exception_type: str) -> ErrorResponse | None:
    """Check for network errors."""
    network_phrases = [
        "connection",
        "timeout",
        "network",
        "503",
        "502",
        "504",
        "unreachable",
    ]
    if any(phrase in error_str for phrase in network_phrases) or exception_type in ["ConnectionError", "TimeoutError"]:
        return ErrorResponse(
            code=ErrorCode.ERR_NETWORK_ERROR,
            message="Network error occurred.",
            suggestion="Please check your connection and try again.",
            severity=ErrorSeverity.MEDIUM,
        )
    return None


# Error classifier dispatch list - order matters for priority
_ERROR_CLASSIFIERS: list[Callable[[str, str], ErrorResponse | None]] = [
    _check_chore_claimed,
    _check_invalid_chore,
    _check_permission_denied,
    _check_user_not_found,
    _check_invalid_state,
    _check_recurrence_pattern,
    _check_quota_exceeded,
    _check_rate_limit,
    _check_authentication,
    _check_network_error,
]


def classify_error_with_response(exception: Exception) -> ErrorResponse:
    """Classify an error and return a structured response with recovery suggestions.

    Args:
        exception: The exception raised during execution

    Returns:
        ErrorResponse with code, message, suggestion, and severity
    """
    error_str = str(exception).lower()
    exception_type = type(exception).__name__

    for classifier in _ERROR_CLASSIFIERS:
        result = classifier(error_str, exception_type)
        if result is not None:
            return result

    # Default to unknown error
    return ErrorResponse(
        code=ErrorCode.ERR_UNKNOWN,
        message="An unexpected error occurred.",
        suggestion="Please try again later. If the problem persists, contact support.",
        severity=ErrorSeverity.MEDIUM,
    )
