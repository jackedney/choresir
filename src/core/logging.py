"""Logging and observability configuration.

This module provides standardized logging utilities and configuration.
All modules should use Python's standard logging library (logging.getLogger(__name__)).

Standard usage:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Message", extra={"key": "value"})

Structured logging utilities:
    log_with_context(logger, "info", "Message", user_id="123", request_id="abc")
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager

from fastapi import FastAPI


def configure_logging() -> None:
    """Configure standard logging."""
    logger = logging.getLogger(__name__)
    logger.info("Logging configured")


def instrument_fastapi(app: FastAPI) -> None:  # noqa: ARG001
    """Placeholder for FastAPI instrumentation."""
    logger = logging.getLogger(__name__)
    logger.info("FastAPI instrumentation placeholder")


def instrument_pydantic_ai() -> None:
    """Placeholder for Pydantic AI instrumentation."""
    logger = logging.getLogger(__name__)
    logger.info("Pydantic AI instrumentation ready")


@contextmanager
def span(name: str) -> Generator[None, None, None]:
    """Create a named logging span for service layer functions.

    Usage:
        with span("user_service.create_user"):
            # Your service logic here
            pass
    """
    _logger = logging.getLogger(__name__)
    _logger.debug("span:start %s", name)
    try:
        yield
    finally:
        _logger.debug("span:end %s", name)


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    **context: object,
) -> None:
    """Log a message with structured context fields.

    Args:
        logger: Logger instance to use
        level: Log level ("debug", "info", "warning", "error", "critical")
        message: Log message
        **context: Additional context fields (user_id, request_id, operation_type, etc.)

    Usage:
        log_with_context(logger, "info", "User created", user_id="123", operation_type="create")
    """
    log_method = getattr(logger, level.lower())
    log_method(message, extra=context)


def log_with_user_context(
    logger: logging.Logger,
    level: str,
    message: str,
    user_id: str | None = None,
    **extra: object,
) -> None:
    """Log a message with user context.

    Args:
        logger: Logger instance to use
        level: Log level ("debug", "info", "warning", "error", "critical")
        message: Log message
        user_id: User ID to include in context
        **extra: Additional context fields

    Usage:
        log_with_user_context(logger, "info", "Action performed", user_id="123", action="claim_chore")
    """
    context = {"user_id": user_id, **extra} if user_id else extra
    log_with_context(logger, level, message, **context)


def log_with_request_context(
    logger: logging.Logger,
    level: str,
    message: str,
    request_id: str | None = None,
    **extra: object,
) -> None:
    """Log a message with request context.

    Args:
        logger: Logger instance to use
        level: Log level ("debug", "info", "warning", "error", "critical")
        message: Log message
        request_id: Request ID to include in context
        **extra: Additional context fields

    Usage:
        log_with_request_context(logger, "info", "Request processed", request_id="abc", status="success")
    """
    context = {"request_id": request_id, **extra} if request_id else extra
    log_with_context(logger, level, message, **context)
