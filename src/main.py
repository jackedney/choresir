"""choresir - Household Operating System living in WhatsApp."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.logging import configure_logfire, instrument_fastapi, instrument_pydantic_ai
from src.core.scheduler import start_scheduler, stop_scheduler
from src.core.schema import sync_schema
from src.interface.webhook import router as webhook_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager."""
    # Startup
    configure_logfire()
    instrument_pydantic_ai()
    await sync_schema(
        admin_email=settings.pocketbase_admin_email,
        admin_password=settings.pocketbase_admin_password,
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
