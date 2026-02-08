"""choresir - Household Operating System living in WhatsApp."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.db_client import close_db
from src.core.logging import configure_logfire, instrument_fastapi, instrument_pydantic_ai
from src.core.scheduler import start_scheduler, stop_scheduler
from src.core.scheduler_tracker import job_tracker
from src.core.schema import init_db
from src.interface.admin_router import router as admin_router
from src.interface.webhook import router as webhook_router
from src.services.house_config_service import ensure_singleton_config, seed_from_env_vars


logger = logging.getLogger(__name__)


async def validate_startup_configuration() -> None:
    """Validate all required credentials.

    Raises:
        ValueError: If required credentials are missing
    """
    logger.info("startup_validation_begin")

    try:
        # Validate required credentials
        settings.require_credential("house_code", "House onboarding code")
        settings.require_credential("house_password", "House onboarding password")
        settings.require_credential("openrouter_api_key", "OpenRouter API key")
        settings.require_credential("admin_password", "Admin password for web interface")
        settings.require_credential("secret_key", "Secret key for session signing")

        logger.info("startup_validation", extra={"stage": "credentials", "status": "ok"})
        logger.info("startup_validation_complete", extra={"status": "ok"})

    except ValueError as e:
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

    # Validate all credentials
    await validate_startup_configuration()

    instrument_pydantic_ai()

    # Initialize SQLite database
    await init_db()

    await seed_from_env_vars()
    await ensure_singleton_config()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    await close_db()


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
app.include_router(admin_router)


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
        "cleanup_expired_invites",
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
