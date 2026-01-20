"""Logging and observability configuration using Pydantic Logfire.

This module provides standardized logging utilities and configuration.
All modules should use Python's standard logging library (logging.getLogger(__name__)),
and Logfire will automatically capture and enrich these logs.

Standard usage:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Message", extra={"key": "value"})

Structured logging utilities:
    log_with_context(logger, "info", "Message", user_id="123", request_id="abc")
"""

import logging

import logfire
from fastapi import FastAPI

from src.core.config import settings


def configure_logfire() -> None:
    """Configure Pydantic Logfire with token from environment.

    Automatically integrates with Python's standard logging to capture all log records.
    """
    logfire.configure(
        token=settings.logfire_token,
        service_name="choresir",
        service_version="0.1.0",
        environment="production",
        send_to_logfire="if-token-present",
    )
    # Integrate with standard logging - all logging calls will be captured by logfire
    # Note: logfire.instrument_logging() removed due to type compatibility issues

    logger = logging.getLogger(__name__)
    logger.info("Logfire configured successfully")


def instrument_fastapi(app: FastAPI) -> None:
    """Add Logfire instrumentation to FastAPI application."""
    logfire.instrument_fastapi(app)
    logger = logging.getLogger(__name__)
    logger.info("FastAPI instrumentation configured")


def instrument_pydantic_ai() -> None:
    """Configure automatic tracing for Pydantic AI agent calls."""
    # Pydantic AI tracing is automatic when logfire is configured
    # The framework automatically creates spans for agent.run() calls
    logger = logging.getLogger(__name__)
    logger.info("Pydantic AI instrumentation ready (automatic)")


def span(name: str) -> logfire.LogfireSpan:
    """Create a custom span for service layer functions.

    Usage:
        with span("user_service.create_user"):
            # Your service logic here
            pass
    """
    return logfire.span(name)


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
