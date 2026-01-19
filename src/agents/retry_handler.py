"""Intelligent retry handler for agent execution with circuit breaker pattern."""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior


logger = logging.getLogger(__name__)


class ErrorRetryability(Enum):
    """Classification of whether an error should be retried."""

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    backoff_multiplier: float = 2.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown: float = 60.0


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker to prevent excessive retries on persistent failures."""

    def __init__(self, threshold: int = 5, cooldown: float = 60.0) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitBreakerState.CLOSED

    def record_success(self) -> None:
        """Record a successful request."""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                extra={"failure_count": self.failure_count, "cooldown": self.cooldown},
            )

    def can_attempt(self) -> bool:
        """Check if a request can be attempted."""
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            # Check if cooldown period has passed
            if time.time() - self.last_failure_time >= self.cooldown:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("circuit_breaker_half_open", extra={"cooldown_elapsed": True})
                return True
            return False

        # HALF_OPEN state - allow attempt to test recovery
        return True


class AgentRetryHandler:
    """Handles intelligent retry logic with exponential backoff and circuit breaker."""

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.config = config or RetryConfig()
        self.circuit_breaker = CircuitBreaker(
            threshold=self.config.circuit_breaker_threshold,
            cooldown=self.config.circuit_breaker_cooldown,
        )

    def classify_error(self, exception: Exception) -> ErrorRetryability:
        """Classify an error to determine if it should be retried.

        Args:
            exception: The exception to classify

        Returns:
            ErrorRetryability indicating if the error is retryable
        """
        error_str = str(exception).lower()
        exception_type = type(exception).__name__

        # Non-retryable: Authentication and authorization errors
        if any(
            phrase in error_str
            for phrase in [
                "authentication failed",
                "invalid api key",
                "unauthorized",
                "invalid token",
                "401",
                "403",
            ]
        ) or exception_type in ["AuthenticationError", "PermissionError"]:
            return ErrorRetryability.NON_RETRYABLE

        # Non-retryable: Validation errors and bad requests
        if any(
            phrase in error_str
            for phrase in [
                "validation error",
                "invalid input",
                "bad request",
                "400",
            ]
        ) or exception_type in ["ValueError", "ValidationError", "KeyError"]:
            return ErrorRetryability.NON_RETRYABLE

        # Non-retryable: Resource not found
        if "404" in error_str or "not found" in error_str:
            return ErrorRetryability.NON_RETRYABLE

        # Retryable: Rate limits
        if any(
            phrase in error_str
            for phrase in [
                "rate limit",
                "too many requests",
                "rate_limit_exceeded",
                "throttled",
                "429",
            ]
        ):
            return ErrorRetryability.RETRYABLE

        # Retryable: Temporary service issues
        if any(
            phrase in error_str
            for phrase in [
                "quota exceeded",
                "insufficient credits",
                "service unavailable",
                "503",
                "502",
                "504",
            ]
        ):
            return ErrorRetryability.RETRYABLE

        # Retryable: Network and timeout errors
        if any(
            phrase in error_str
            for phrase in [
                "timeout",
                "connection",
                "network",
                "unreachable",
            ]
        ) or exception_type in ["ConnectionError", "TimeoutError"]:
            return ErrorRetryability.RETRYABLE

        # Retryable: Pydantic AI retry exceptions
        if isinstance(exception, ModelRetry | UnexpectedModelBehavior):
            return ErrorRetryability.RETRYABLE

        # Default to non-retryable for unknown errors to avoid infinite loops
        return ErrorRetryability.NON_RETRYABLE

    def calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for the given attempt.

        Args:
            attempt: The attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = self.config.base_delay * (self.config.backoff_multiplier**attempt)
        return min(delay, 30.0)  # Cap at 30 seconds

    async def execute_with_retry(
        self,
        func: object,
        *args: object,
        **kwargs: object,
    ) -> object:
        """Execute a function with intelligent retry logic.

        Args:
            func: The async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            The result of the function

        Raises:
            The last exception if all retries are exhausted
        """
        last_exception = None

        for attempt in range(self.config.max_attempts):
            # Check circuit breaker
            if not self.circuit_breaker.can_attempt():
                logger.warning(
                    "circuit_breaker_blocked",
                    extra={"attempt": attempt, "state": self.circuit_breaker.state.value},
                )
                raise RuntimeError("Circuit breaker is open. Service temporarily unavailable.")

            try:
                result = await func(*args, **kwargs)
                self.circuit_breaker.record_success()
                if attempt > 0:
                    logger.info("agent_retry_success", extra={"attempt": attempt, "total_attempts": attempt + 1})
                return result

            except Exception as e:
                last_exception = e
                retryability = self.classify_error(e)
                error_type = type(e).__name__

                # Log the error
                logger.warning(
                    "agent_error",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": self.config.max_attempts,
                        "error_type": error_type,
                        "error_message": str(e),
                        "retryable": retryability.value,
                    },
                )

                # If error is non-retryable, fail immediately
                if retryability == ErrorRetryability.NON_RETRYABLE:
                    logger.info(
                        "agent_retry_skipped",
                        extra={"attempt": attempt + 1, "error_type": error_type, "reason": "non_retryable_error"},
                    )
                    self.circuit_breaker.record_failure()
                    raise

                # If this was the last attempt, fail
                if attempt >= self.config.max_attempts - 1:
                    logger.error(
                        "agent_retry_exhausted",
                        extra={"attempts": self.config.max_attempts, "error_type": error_type, "error_message": str(e)},
                    )
                    self.circuit_breaker.record_failure()
                    raise

                # Calculate delay and retry
                delay = self.calculate_delay(attempt)
                logger.info(
                    "agent_retry",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": self.config.max_attempts,
                        "error_type": error_type,
                        "delay_seconds": delay,
                        "next_attempt": attempt + 2,
                    },
                )

                await asyncio.sleep(delay)

        # Should not reach here, but raise the last exception if we do
        if last_exception:
            raise last_exception
        # This line is unreachable but ensures the function always returns or raises
        return None  # type: ignore[unreachable]


# Global retry handler instance
_retry_handler: AgentRetryHandler | None = None


def get_retry_handler() -> AgentRetryHandler:
    """Get or create the global retry handler instance."""
    global _retry_handler  # noqa: PLW0603
    if _retry_handler is None:
        _retry_handler = AgentRetryHandler()
    return _retry_handler
