"""choresir - Household Operating System living in WhatsApp."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.core.schema import sync_schema
from src.interface.webhook import router as webhook_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager."""
    # Startup
    await sync_schema()
    yield
    # Shutdown


app = FastAPI(
    title="choresir",
    description="Household Operating System living in WhatsApp",
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(webhook_router)


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(content={"status": "healthy"}, status_code=200)
