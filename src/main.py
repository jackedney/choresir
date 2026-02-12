"""choresir - Household Operating System living in WhatsApp."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.core.config import constants, settings
from src.core.db_client import init_db
from src.core.logging import configure_logging, instrument_fastapi, instrument_pydantic_ai
from src.core.module_registry import get_modules, register_module
from src.core.scheduler import start_scheduler, stop_scheduler
from src.core.scheduler_tracker import job_tracker
from src.interface.admin_router import router as admin_router
from src.interface.webhook import router as webhook_router
from src.modules.onboarding import OnboardingModule
from src.modules.pantry import PantryModule
from src.modules.tasks import TasksModule
from src.services.house_config_service import ensure_singleton_config, seed_from_env_vars


logger = logging.getLogger(__name__)


async def validate_startup_configuration() -> None:
    """Validate required startup credentials."""
    logger.info("startup_validation_begin")

    try:
        # Validate required credentials
        settings.require_credential("openrouter_api_key", "OpenRouter API key")
        settings.require_credential("admin_password", "Admin password for web interface")
        settings.require_credential("secret_key", "Secret key for session signing")

        logger.info("startup_validation", extra={"stage": "credentials", "status": "ok"})

        logger.info("startup_validation_complete", extra={"status": "ok"})

    except ValueError as e:
        logger.critical("Startup validation failed: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.critical("Unexpected error during startup validation: %s", e)
        sys.exit(1)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager."""
    # Startup
    # Configure logging first so validation logs are captured
    configure_logging()

    # Validate all credentials
    await validate_startup_configuration()

    instrument_pydantic_ai()

    # Register modules before init_db so module table schemas are included
    register_module(TasksModule())
    register_module(PantryModule())
    register_module(OnboardingModule())

    await init_db()
    await seed_from_env_vars()
    await ensure_singleton_config()

    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title=settings.bot_name,
    description=settings.bot_description,
    version="0.1.0",
    lifespan=lifespan,
)

# Instrument FastAPI with Logfire
instrument_fastapi(app)

# Set up templates
templates = Jinja2Templates(directory=str(constants.PROJECT_ROOT / "templates"))

# Register routers
app.include_router(webhook_router)
app.include_router(admin_router)


@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    """Landing page."""
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(content={"status": "healthy"}, status_code=200)


@app.get("/health/scheduler")
async def scheduler_health_check() -> JSONResponse:
    """Scheduler health check endpoint with job statuses."""
    # Core job names
    core_job_names = ["expire_workflows", "cleanup_group_context"]

    # Get job names from registered modules
    module_job_names = []
    for module in get_modules().values():
        for job in module.get_scheduled_jobs():
            module_job_names.append(job.id)

    # Combine core jobs and module jobs
    job_names = core_job_names + module_job_names

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
