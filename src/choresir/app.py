"""FastAPI app factory, lifespan, and exception handlers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from choresir.admin.app import create_admin_app
from choresir.agent.agent import AgentDeps, create_agent
from choresir.config import Settings
from choresir.db import create_engine, create_session_factory
from choresir.errors import RateLimitExceededError, WebhookAuthError
from choresir.models.job import MessageJob
from choresir.scheduler.setup import create_scheduler, register_schedules
from choresir.services.member_service import MemberService
from choresir.services.messaging import WAHAClient
from choresir.services.task_service import TaskService
from choresir.webhook.router import create_webhook_router
from choresir.worker.processor import message_worker_loop


async def run_migrations(engine: AsyncEngine, database_url: str) -> None:
    cfg = AlembicConfig(str(Path("alembic.ini")))
    cfg.set_main_option("sqlalchemy.url", database_url)

    def _run(connection) -> None:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    async with engine.begin() as conn:
        await conn.run_sync(_run)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((TimeoutError, httpx.RequestError)),
    reraise=True,
)
async def call_agent_with_retry(agent, message: str, deps: AgentDeps) -> str:
    result = await agent.run(message, deps=deps)
    return result.output


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully wired FastAPI application with no global mutable state."""
    settings = settings or Settings()

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_migrations(engine, settings.database_url)

        async with httpx.AsyncClient(base_url=settings.waha_url, timeout=10.0) as http:
            sender = WAHAClient(
                settings.waha_url,
                settings.waha_api_key,
                "default",
                http,
            )

            scheduler = create_scheduler()
            async with scheduler:
                await register_schedules(
                    scheduler, session_factory, sender, settings.group_chat_id
                )
                await scheduler.start_in_background()

                agent = create_agent(settings)

                async def process_message(job: MessageJob) -> None:
                    async with session_factory() as session:
                        task_service = TaskService(
                            session, sender, settings.max_takeovers_per_week
                        )
                        member_service = MemberService(session)
                        deps = AgentDeps(
                            task_service=task_service,
                            member_service=member_service,
                            sender_id=job.sender_id,
                        )
                        response = await call_agent_with_retry(agent, job.body, deps)
                        await sender.send(job.group_id, response)

                worker_task = asyncio.create_task(
                    message_worker_loop(session_factory, process_message, settings)
                )

                app.state.session_factory = session_factory
                app.state.sender = sender

                yield

                worker_task.cancel()
                await asyncio.gather(worker_task, return_exceptions=True)

        await engine.dispose()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(WebhookAuthError)
    async def webhook_auth_handler(
        request: Request, exc: WebhookAuthError
    ) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(
        request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    webhook_router = create_webhook_router(
        session_factory, settings.waha_webhook_secret
    )
    app.include_router(webhook_router)

    admin_app = create_admin_app(settings, session_factory)
    app.mount("/admin", admin_app)

    return app
