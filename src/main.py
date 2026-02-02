"""choresir - Household Operating System living in WhatsApp."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.db_client import get_client
from src.core.logging import configure_logfire, instrument_fastapi, instrument_pydantic_ai
from src.core.redis_client import redis_client
from src.core.scheduler import start_scheduler, stop_scheduler
from src.core.scheduler_tracker import job_tracker
from src.core.schema import sync_schema
from src.interface.webhook import router as webhook_router


logger = logging.getLogger(__name__)


async def check_pocketbase_connectivity() -> None:
    """Verify PocketBase connectivity and authentication.

    Raises:
        ConnectionError: If unable to connect or authenticate
    """
    try:
        client = get_client()
        # Verify we have an authenticated connection
        if not client.auth_store.token:
            raise ConnectionError("PocketBase authentication failed: No token present")

        logger.info("startup_validation", extra={"service": "pocketbase", "status": "ok"})
    except Exception as e:
        logger.error("startup_validation", extra={"service": "pocketbase", "status": "failed", "error": str(e)})
        raise ConnectionError(f"PocketBase connectivity check failed: {e}") from e


async def check_redis_connectivity() -> None:
    """Verify Redis connectivity (optional service).

    Only checks if Redis is configured. Logs warning if unavailable but doesn't fail.

    Raises:
        ConnectionError: Only if Redis is configured but connectivity test fails critically
    """
    if not redis_client.is_available:
        logger.info("startup_validation", extra={"service": "redis", "status": "disabled"})
        return

    try:
        result = await redis_client.ping()
        if result:
            logger.info("startup_validation", extra={"service": "redis", "status": "ok"})
        else:
            logger.warning("startup_validation", extra={"service": "redis", "status": "unavailable"})
    except Exception as e:
        logger.warning("startup_validation", extra={"service": "redis", "status": "unavailable", "error": str(e)})


async def validate_startup_configuration() -> None:
    """Validate all required credentials and external service connectivity.

    Performs comprehensive startup validation:
    - Validates all required credentials
    - Tests connectivity to external services
    - Fails fast with clear error messages

    Raises:
        ValueError: If required credentials are missing
        ConnectionError: If external services are unreachable
    """
    logger.info("startup_validation_begin")

    try:
        # Validate required credentials
        settings.require_credential("house_code", "House onboarding code")
        settings.require_credential("house_password", "House onboarding password")
        settings.require_credential("openrouter_api_key", "OpenRouter API key")
        settings.require_credential("pocketbase_url", "PocketBase URL")
        settings.require_credential("pocketbase_admin_email", "PocketBase admin email")
        settings.require_credential("pocketbase_admin_password", "PocketBase admin password")

        logger.info("startup_validation", extra={"stage": "credentials", "status": "ok"})

        # Check external service connectivity
        await check_pocketbase_connectivity()
        await check_redis_connectivity()

        logger.info("startup_validation_complete", extra={"status": "ok"})

    except (ValueError, ConnectionError) as e:
        logger.error("startup_validation_failed", extra={"error": str(e)})
        print(f"\n❌ Startup validation failed: {e}\n", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    except Exception as e:
        logger.error("startup_validation_unexpected_error", extra={"error": str(e)})
        print(f"\n❌ Unexpected error during startup validation: {e}\n", file=sys.stderr)  # noqa: T201
        sys.exit(1)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager."""
    # Startup
    # Configure logging first so validation logs are captured
    configure_logfire()

    # Validate all credentials and external service connectivity
    await validate_startup_configuration()

    instrument_pydantic_ai()
    # Ensure credentials are present (validated in validate_startup_configuration)
    admin_email = settings.require_credential("pocketbase_admin_email", "PocketBase Admin Email")
    admin_password = settings.require_credential("pocketbase_admin_password", "PocketBase Admin Password")

    await sync_schema(
        admin_email=admin_email,
        admin_password=admin_password,
    )
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="choresir",
    description="Household Operating System living in WhatsApp",
    version="0.1.0",
    lifespan=lifespan,
)

# Instrument FastAPI with Logfire
instrument_fastapi(app)

# Register routers
app.include_router(webhook_router)


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(content={"status": "healthy"}, status_code=200)


@app.get("/health/scheduler")
async def scheduler_health_check() -> JSONResponse:
    """Scheduler health check endpoint with job statuses."""
    # Get status for all tracked jobs
    job_names = [
        "overdue_reminders",
        "daily_report",
        "weekly_leaderboard",
        "personal_chore_reminders",
        "auto_verify_personal",
    ]

    job_statuses = {}
    for job_name in job_names:
        job_statuses[job_name] = await job_tracker.get_job_status(job_name)

    # Get dead letter queue
    dlq = job_tracker.get_dead_letter_queue()

    # Determine overall health
    has_failures = any(status["consecutive_failures"] > 0 for status in job_statuses.values())

    overall_status = "degraded" if has_failures else "healthy"
    if len(dlq) > 0:
        overall_status = "critical"

    return JSONResponse(
        content={
            "status": overall_status,
            "jobs": job_statuses,
            "dead_letter_queue_size": len(dlq),
            "dead_letter_queue": dlq,
        },
        status_code=200 if overall_status == "healthy" else 503,
    )
