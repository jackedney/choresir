"""Logging and observability configuration using Pydantic Logfire."""

import logfire
from fastapi import FastAPI

from src.core.config import settings


def configure_logfire() -> None:
    """Configure Pydantic Logfire with token from environment."""
    logfire.configure(
        token=settings.logfire_token,
        service_name="choresir",
        service_version="0.1.0",
        environment="production",
        send_to_logfire="if-token-present",
    )
    logfire.info("Logfire configured successfully")


def instrument_fastapi(app: FastAPI) -> None:
    """Add Logfire instrumentation to FastAPI application."""
    logfire.instrument_fastapi(app)
    logfire.info("FastAPI instrumentation configured")


def instrument_pydantic_ai() -> None:
    """Configure automatic tracing for Pydantic AI agent calls."""
    # Pydantic AI tracing is automatic when logfire is configured
    # The framework automatically creates spans for agent.run() calls
    logfire.info("Pydantic AI instrumentation ready (automatic)")


def span(name: str) -> logfire.LogfireSpan:
    """Create a custom span for service layer functions.

    Usage:
        with span("user_service.create_user"):
            # Your service logic here
            pass
    """
    return logfire.span(name)


# Convenience functions for logging
def log_info(message: str) -> None:
    """Log an info-level message."""
    logfire.info(message)


def log_warning(message: str) -> None:
    """Log a warning-level message."""
    logfire.warn(message)


def log_error(message: str) -> None:
    """Log an error-level message."""
    logfire.error(message)


def log_debug(message: str) -> None:
    """Log a debug-level message."""
    logfire.debug(message)
