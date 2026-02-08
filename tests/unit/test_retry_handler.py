"""Unit tests for the agent retry handler."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.retry_handler import (
    AgentRetryHandler,
    CircuitBreaker,
    CircuitBreakerState,
    ErrorRetryability,
    RetryConfig,
)


@pytest.fixture(autouse=True)
def mock_asyncio_sleep():
    """Mock asyncio.sleep to avoid actual delays in retry tests."""
    with patch("src.agents.retry_handler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep


@pytest.mark.unit
class TestAgentRetryHandler:
    """Tests for intelligent retry logic with circuit breaker."""

    @pytest.fixture
    def retry_handler(self):
        """Create a retry handler with test configuration."""
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,  # Small delay for tests
            backoff_multiplier=2.0,
            circuit_breaker_threshold=2,
            circuit_breaker_cooldown=0.1,
        )
        return AgentRetryHandler(config)

    def test_classify_error_retryable_rate_limit(self, retry_handler):
        """Test classification of rate limit errors as retryable."""
        error = Exception("Rate limit exceeded")
        result = retry_handler.classify_error(error)
        assert result == ErrorRetryability.RETRYABLE

    def test_classify_error_retryable_network(self, retry_handler):
        """Test classification of network errors as retryable."""
        error = ConnectionError("Connection timeout")
        result = retry_handler.classify_error(error)
        assert result == ErrorRetryability.RETRYABLE

    def test_classify_error_non_retryable_auth(self, retry_handler):
        """Test classification of auth errors as non-retryable."""
        error = Exception("Invalid API key")
        result = retry_handler.classify_error(error)
        assert result == ErrorRetryability.NON_RETRYABLE

    def test_classify_error_non_retryable_validation(self, retry_handler):
        """Test classification of validation errors as non-retryable."""
        error = ValueError("Invalid input")
        result = retry_handler.classify_error(error)
        assert result == ErrorRetryability.NON_RETRYABLE

    def test_calculate_delay_exponential_backoff(self, retry_handler):
        """Test exponential backoff calculation."""
        # First retry: 0.01 * 2^0 = 0.01
        assert retry_handler.calculate_delay(0) == 0.01
        # Second retry: 0.01 * 2^1 = 0.02
        assert retry_handler.calculate_delay(1) == 0.02
        # Third retry: 0.01 * 2^2 = 0.04
        assert retry_handler.calculate_delay(2) == 0.04

    @pytest.mark.asyncio
    async def test_execute_with_retry_success_first_attempt(self, retry_handler):
        """Test successful execution on first attempt."""
        mock_func = AsyncMock(return_value="success")

        result = await retry_handler.execute_with_retry(mock_func)

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_success_after_retries(self, retry_handler):
        """Test successful execution after retries."""
        mock_func = AsyncMock()
        # Fail twice, then succeed
        mock_func.side_effect = [
            Exception("Rate limit"),
            Exception("Rate limit"),
            "success",
        ]

        result = await retry_handler.execute_with_retry(mock_func)

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_with_retry_non_retryable_error_fails_immediately(self, retry_handler):
        """Test that non-retryable errors fail immediately without retries."""
        mock_func = AsyncMock(side_effect=ValueError("Invalid input"))

        with pytest.raises(ValueError, match="Invalid input"):
            await retry_handler.execute_with_retry(mock_func)

        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_exhausts_retries(self, retry_handler):
        """Test that retries are exhausted for persistent failures."""
        mock_func = AsyncMock(side_effect=Exception("Rate limit"))

        with pytest.raises(Exception, match="Rate limit"):
            await retry_handler.execute_with_retry(mock_func)

        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_with_retry_logs_attempts(self, retry_handler):
        """Test that retry attempts are logged."""
        mock_func = AsyncMock(side_effect=[Exception("Rate limit"), "success"])

        with patch("src.agents.retry_handler.logger") as mock_logger:
            result = await retry_handler.execute_with_retry(mock_func)

            assert result == "success"
            # Should log warning for first error and info for retry success
            assert mock_logger.warning.called
            assert mock_logger.info.called


@pytest.mark.unit
class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker with test configuration."""
        return CircuitBreaker(threshold=2, cooldown=0.1)

    def test_circuit_breaker_starts_closed(self, circuit_breaker):
        """Test that circuit breaker starts in CLOSED state."""
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.can_attempt() is True

    def test_circuit_breaker_opens_after_threshold(self, circuit_breaker):
        """Test that circuit breaker opens after threshold failures."""
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.can_attempt() is True

        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitBreakerState.OPEN
        assert circuit_breaker.can_attempt() is False

    def test_circuit_breaker_half_open_after_cooldown(self, circuit_breaker):
        """Test that circuit breaker moves to HALF_OPEN after cooldown."""
        # Open the circuit
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitBreakerState.OPEN

        # Wait for cooldown
        time.sleep(0.15)

        # Should now be HALF_OPEN
        assert circuit_breaker.can_attempt() is True
        assert circuit_breaker.state == CircuitBreakerState.HALF_OPEN

    def test_circuit_breaker_closes_on_success(self, circuit_breaker):
        """Test that circuit breaker closes on successful request."""
        # Open the circuit
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()

        # Record success
        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_requests_when_open(self):
        """Test that circuit breaker blocks requests when open."""
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            circuit_breaker_threshold=2,
            circuit_breaker_cooldown=10.0,  # Long cooldown
        )
        handler = AgentRetryHandler(config)

        # Need 2 separate calls that fail to open circuit
        # Each call will attempt 3 times before failing
        mock_func1 = AsyncMock(side_effect=Exception("Rate limit"))
        mock_func2 = AsyncMock(side_effect=Exception("Rate limit"))

        # First call - will fail all 3 attempts, circuit breaker records 1 failure
        with pytest.raises(Exception, match="Rate limit"):
            await handler.execute_with_retry(mock_func1)

        # Second call - will fail and open circuit after hitting threshold
        with pytest.raises(Exception, match="Rate limit"):
            await handler.execute_with_retry(mock_func2)

        # Circuit should now be open, next call should fail immediately
        mock_func3 = AsyncMock(side_effect=Exception("Rate limit"))

        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            await handler.execute_with_retry(mock_func3)

        # Should not have called the function
        assert mock_func3.call_count == 0
