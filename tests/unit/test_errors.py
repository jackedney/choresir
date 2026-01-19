"""Unit tests for error classification utilities."""

import pytest

from src.core.errors import ErrorCategory, ErrorCode, ErrorSeverity, classify_agent_error, classify_error_with_response


@pytest.mark.unit
class TestClassifyAgentError:
    """Tests for classify_agent_error function."""

    def test_openrouter_quota_exceeded(self):
        """Test classification of OpenRouter quota exceeded error."""
        exception = Exception("OpenRouter API error: quota exceeded for this model")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.SERVICE_QUOTA_EXCEEDED
        assert "quota" in message.lower()
        assert "try again later" in message.lower()

    def test_insufficient_credits(self):
        """Test classification of insufficient credits error."""
        exception = Exception("API error: insufficient credits remaining")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.SERVICE_QUOTA_EXCEEDED
        assert "quota" in message.lower()

    def test_credit_limit_reached(self):
        """Test classification of credit limit error."""
        exception = Exception("Credit limit reached. Please add more credits to your account.")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.SERVICE_QUOTA_EXCEEDED
        assert "quota" in message.lower()

    def test_out_of_credits(self):
        """Test classification of out of credits error."""
        exception = Exception("Out of credits. Your account has exhausted its credits.")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.SERVICE_QUOTA_EXCEEDED

    def test_rate_limit_exceeded(self):
        """Test classification of rate limit exceeded error."""
        exception = Exception("Rate limit exceeded. Please try again in 60 seconds.")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.RATE_LIMIT_EXCEEDED
        assert "too many requests" in message.lower()
        assert "wait" in message.lower()

    def test_too_many_requests(self):
        """Test classification of too many requests error."""
        exception = Exception("HTTP 429: Too many requests")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.RATE_LIMIT_EXCEEDED
        assert "too many requests" in message.lower()

    def test_rate_limit_throttled(self):
        """Test classification of throttled requests."""
        exception = Exception("Request throttled due to rate limits")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.RATE_LIMIT_EXCEEDED

    def test_authentication_failed_invalid_key(self):
        """Test classification of invalid API key error."""
        exception = Exception("Invalid API key provided")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.AUTHENTICATION_FAILED
        assert "authentication" in message.lower()
        assert "contact support" in message.lower()

    def test_authentication_failed_unauthorized(self):
        """Test classification of unauthorized error."""
        exception = Exception("HTTP 401: Unauthorized access")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.AUTHENTICATION_FAILED

    def test_authentication_failed_invalid_token(self):
        """Test classification of invalid token error."""
        exception = Exception("Authentication error: invalid token")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.AUTHENTICATION_FAILED

    def test_authentication_error_type(self):
        """Test classification of AuthenticationError exception type."""

        class AuthenticationError(Exception):
            pass

        exception = AuthenticationError("Authentication failed")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.AUTHENTICATION_FAILED

    def test_permission_error_type(self):
        """Test classification of PermissionError exception type."""
        exception = PermissionError("Permission denied")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.AUTHENTICATION_FAILED

    def test_network_connection_error(self):
        """Test classification of connection error."""
        exception = Exception("Connection error: Unable to reach server")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.NETWORK_ERROR
        assert "network" in message.lower()
        assert "connection" in message.lower()

    def test_network_timeout_error(self):
        """Test classification of timeout error."""
        exception = Exception("Request timeout after 30 seconds")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.NETWORK_ERROR

    def test_network_503_error(self):
        """Test classification of HTTP 503 error."""
        exception = Exception("HTTP 503: Service unavailable")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.NETWORK_ERROR

    def test_network_502_error(self):
        """Test classification of HTTP 502 error."""
        exception = Exception("HTTP 502: Bad gateway")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.NETWORK_ERROR

    def test_network_504_error(self):
        """Test classification of HTTP 504 error."""
        exception = Exception("HTTP 504: Gateway timeout")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.NETWORK_ERROR

    def test_connection_error_type(self):
        """Test classification of ConnectionError exception type."""
        exception = ConnectionError("Failed to establish connection")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.NETWORK_ERROR

    def test_timeout_error_type(self):
        """Test classification of TimeoutError exception type."""
        exception = TimeoutError("Operation timed out")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.NETWORK_ERROR

    def test_unknown_error(self):
        """Test classification of unknown error."""
        exception = Exception("Something unexpected happened")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.UNKNOWN
        assert "unexpected error" in message.lower()
        assert "try again later" in message.lower()

    def test_generic_exception(self):
        """Test classification of generic exception."""
        exception = ValueError("Invalid input provided")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.UNKNOWN

    def test_empty_exception_message(self):
        """Test classification of exception with empty message."""
        exception = Exception("")
        category, message = classify_agent_error(exception)

        assert category == ErrorCategory.UNKNOWN
        assert len(message) > 0

    def test_case_insensitive_matching(self):
        """Test that error matching is case-insensitive."""
        exception = Exception("RATE LIMIT EXCEEDED")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.RATE_LIMIT_EXCEEDED

    def test_partial_message_matching(self):
        """Test that partial message matching works."""
        exception = Exception("API request failed with rate_limit_exceeded error code")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.RATE_LIMIT_EXCEEDED

    def test_openrouter_specific_quota_message(self):
        """Test OpenRouter-specific quota exceeded message format."""
        exception = Exception(
            "OpenRouter error (402): Insufficient credits. "
            "Please add credits to your account at https://openrouter.ai/credits"
        )
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.SERVICE_QUOTA_EXCEEDED

    def test_openrouter_rate_limit_message(self):
        """Test OpenRouter-specific rate limit message format."""
        exception = Exception("OpenRouter error (429): Rate limit exceeded for model anthropic/claude-3.5-sonnet")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.RATE_LIMIT_EXCEEDED

    def test_multiple_error_indicators(self):
        """Test error with multiple indicators prioritizes first match."""
        # This has both "quota exceeded" and "rate limit" but should match quota first
        exception = Exception("Quota exceeded due to rate limit")
        category, _ = classify_agent_error(exception)

        assert category == ErrorCategory.SERVICE_QUOTA_EXCEEDED

    def test_return_type(self):
        """Test that function returns correct tuple type."""
        exception = Exception("test error")
        result = classify_agent_error(exception)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], ErrorCategory)
        assert isinstance(result[1], str)

    def test_user_friendly_messages_are_distinct(self):
        """Test that different error categories have different user messages."""
        quota_error = Exception("quota exceeded")
        rate_error = Exception("rate limit exceeded")
        auth_error = Exception("authentication failed")
        network_error = Exception("connection error")
        unknown_error = Exception("random error")

        _, quota_msg = classify_agent_error(quota_error)
        _, rate_msg = classify_agent_error(rate_error)
        _, auth_msg = classify_agent_error(auth_error)
        _, network_msg = classify_agent_error(network_error)
        _, unknown_msg = classify_agent_error(unknown_error)

        messages = [quota_msg, rate_msg, auth_msg, network_msg, unknown_msg]
        # All messages should be unique
        assert len(messages) == len(set(messages))


@pytest.mark.unit
class TestClassifyErrorWithResponse:
    """Tests for classify_error_with_response function."""

    def test_chore_already_claimed_error(self):
        """Test classification of chore already claimed error."""
        exception = Exception("Cannot claim chore, it's already claimed")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_CHORE_ALREADY_CLAIMED
        assert "already been claimed" in response.message
        assert "/list chores" in response.suggestion
        assert response.severity == ErrorSeverity.LOW

    def test_invalid_chore_id_error(self):
        """Test classification of invalid chore ID error."""
        exception = Exception("Chore not found")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_INVALID_CHORE_ID
        assert "couldn't find" in response.message
        assert "/list chores" in response.suggestion
        assert response.severity == ErrorSeverity.LOW

    def test_permission_denied_error(self):
        """Test classification of permission denied error."""
        exception = PermissionError("User does not have permission")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_PERMISSION_DENIED
        assert "permission" in response.message.lower()
        assert "admin" in response.suggestion.lower()
        assert response.severity == ErrorSeverity.MEDIUM

    def test_user_not_found_error(self):
        """Test classification of user not found error."""
        exception = KeyError("User not found in database")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_USER_NOT_FOUND
        assert "not found" in response.message.lower()
        assert "/help" in response.suggestion
        assert response.severity == ErrorSeverity.MEDIUM

    def test_invalid_state_transition_error(self):
        """Test classification of invalid state transition error."""
        exception = ValueError("Cannot transition from CLAIMED to AVAILABLE")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_INVALID_STATE_TRANSITION
        assert "cannot be performed" in response.message.lower()
        assert "/list chores" in response.suggestion
        assert response.severity == ErrorSeverity.LOW

    def test_invalid_recurrence_pattern_error(self):
        """Test classification of invalid recurrence pattern error."""
        exception = Exception("Invalid recurrence pattern format")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_INVALID_RECURRENCE_PATTERN
        assert "recurrence" in response.message.lower()
        assert "daily" in response.suggestion
        assert response.severity == ErrorSeverity.LOW

    def test_quota_exceeded_error(self):
        """Test classification of quota exceeded error."""
        exception = Exception("Quota exceeded for this service")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_SERVICE_QUOTA_EXCEEDED
        assert "quota" in response.message.lower()
        assert "try again later" in response.suggestion.lower()
        assert response.severity == ErrorSeverity.HIGH

    def test_rate_limit_error(self):
        """Test classification of rate limit error."""
        exception = Exception("Rate limit exceeded")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_RATE_LIMIT_EXCEEDED
        assert "too many requests" in response.message.lower()
        assert "wait" in response.suggestion.lower()
        assert response.severity == ErrorSeverity.MEDIUM

    def test_authentication_error(self):
        """Test classification of authentication error."""
        exception = Exception("Invalid API key")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_AUTHENTICATION_FAILED
        assert "authentication" in response.message.lower()
        assert "support" in response.suggestion.lower()
        assert response.severity == ErrorSeverity.CRITICAL

    def test_network_error(self):
        """Test classification of network error."""
        exception = ConnectionError("Connection failed")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_NETWORK_ERROR
        assert "network" in response.message.lower()
        assert "connection" in response.suggestion.lower()
        assert response.severity == ErrorSeverity.MEDIUM

    def test_unknown_error(self):
        """Test classification of unknown error."""
        exception = Exception("Something completely unexpected")
        response = classify_error_with_response(exception)

        assert response.code == ErrorCode.ERR_UNKNOWN
        assert "unexpected" in response.message.lower()
        assert "try again" in response.suggestion.lower()
        assert response.severity == ErrorSeverity.MEDIUM

    def test_response_has_all_required_fields(self):
        """Test that ErrorResponse has all required fields."""
        exception = Exception("Test error")
        response = classify_error_with_response(exception)

        assert hasattr(response, "code")
        assert hasattr(response, "message")
        assert hasattr(response, "suggestion")
        assert hasattr(response, "severity")
        assert isinstance(response.code, str)
        assert isinstance(response.message, str)
        assert isinstance(response.suggestion, str)
        assert isinstance(response.severity, ErrorSeverity)

    def test_chore_specific_errors_have_low_severity(self):
        """Test that chore-specific errors have appropriate low severity."""
        chore_claimed = Exception("Already claimed")
        invalid_chore = Exception("Chore not found")
        invalid_state = ValueError("Cannot transition")

        assert classify_error_with_response(chore_claimed).severity == ErrorSeverity.LOW
        assert classify_error_with_response(invalid_chore).severity == ErrorSeverity.LOW
        assert classify_error_with_response(invalid_state).severity == ErrorSeverity.LOW

    def test_all_suggestions_are_actionable(self):
        """Test that all suggestions provide actionable guidance."""
        exceptions = [
            Exception("Already claimed"),
            Exception("Chore not found"),
            PermissionError("No permission"),
            KeyError("User not found"),
            ValueError("Cannot transition"),
            Exception("Invalid pattern"),
        ]

        for exc in exceptions:
            response = classify_error_with_response(exc)
            # Suggestions should be non-empty and provide guidance
            assert len(response.suggestion) > 0
            assert any(
                keyword in response.suggestion.lower() for keyword in ["try", "use", "contact", "check", "make sure"]
            )
