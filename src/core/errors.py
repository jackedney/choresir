"""Error classification utilities for agent execution errors."""

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


def classify_error_with_response(exception: Exception) -> ErrorResponse:
    """Classify an error and return a structured response with recovery suggestions.

    Args:
        exception: The exception raised during execution

    Returns:
        ErrorResponse with code, message, suggestion, and severity
    """
    error_str = str(exception).lower()
    exception_type = type(exception).__name__

    # Check for chore-specific errors by message patterns
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

    # Check for permission errors
    if exception_type == "PermissionError" or "permission denied" in error_str or "does not belong to" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_PERMISSION_DENIED,
            message="You don't have permission for this action.",
            suggestion="Contact your household admin if you think this is an error.",
            severity=ErrorSeverity.MEDIUM,
        )

    # Check for user not found
    if exception_type == "KeyError" and ("user" in error_str or "not found" in error_str):
        return ErrorResponse(
            code=ErrorCode.ERR_USER_NOT_FOUND,
            message="User not found.",
            suggestion="Make sure you're registered. Try `/help` for more information.",
            severity=ErrorSeverity.MEDIUM,
        )

    # Check for invalid state transitions
    if exception_type == "ValueError" and ("cannot" in error_str or "invalid state" in error_str):
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_STATE_TRANSITION,
            message="This action cannot be performed in the current state.",
            suggestion="Check the chore status with `/list chores` and try again.",
            severity=ErrorSeverity.LOW,
        )

    # Check for recurrence pattern errors
    if "recurrence" in error_str or "pattern" in error_str:
        return ErrorResponse(
            code=ErrorCode.ERR_INVALID_RECURRENCE_PATTERN,
            message="Invalid recurrence pattern.",
            suggestion="Use formats like 'daily', 'weekly', 'every 3 days', or 'Mon,Wed,Fri'.",
            severity=ErrorSeverity.LOW,
        )

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
        return ErrorResponse(
            code=ErrorCode.ERR_SERVICE_QUOTA_EXCEEDED,
            message="The AI service quota has been exceeded.",
            suggestion="Please try again later or contact support.",
            severity=ErrorSeverity.HIGH,
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
        return ErrorResponse(
            code=ErrorCode.ERR_RATE_LIMIT_EXCEEDED,
            message="Too many requests.",
            suggestion="Please wait a moment and try again.",
            severity=ErrorSeverity.MEDIUM,
        )

    # Check for authentication errors
    if (
        any(
            phrase in error_str
            for phrase in [
                "authentication failed",
                "invalid api key",
                "unauthorized",
                "invalid token",
                "api key",
                "401",
            ]
        )
        or exception_type == "AuthenticationError"
    ):
        return ErrorResponse(
            code=ErrorCode.ERR_AUTHENTICATION_FAILED,
            message="Service authentication failed.",
            suggestion="Please contact support.",
            severity=ErrorSeverity.CRITICAL,
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
        return ErrorResponse(
            code=ErrorCode.ERR_NETWORK_ERROR,
            message="Network error occurred.",
            suggestion="Please check your connection and try again.",
            severity=ErrorSeverity.MEDIUM,
        )

    # Default to unknown error
    return ErrorResponse(
        code=ErrorCode.ERR_UNKNOWN,
        message="An unexpected error occurred.",
        suggestion="Please try again later. If the problem persists, contact support.",
        severity=ErrorSeverity.MEDIUM,
    )
