"""FastAPI app factory, lifespan, and exception handlers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from choresir.admin.app import create_admin_app
from choresir.agent.agent import AgentDeps, create_agent
from choresir.config import Settings
from choresir.db import create_engine, create_session_factory
from choresir.errors import RateLimitExceededError, WebhookAuthError
from choresir.models.job import MessageJob
from choresir.scheduler.setup import create_scheduler
from choresir.services.member_service import MemberService
from choresir.services.messaging import WAHAClient
from choresir.services.task_service import TaskService
from choresir.webhook.router import create_webhook_router
from choresir.worker.processor import message_worker_loop


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully wired FastAPI application with no global mutable state."""
    settings = settings or Settings()

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            base_url=settings.waha_url, timeout=10.0
        ) as http:
            sender = WAHAClient(
                settings.waha_url,
                settings.waha_api_key,
                "default",
                http,
            )

            scheduler = await create_scheduler(
                session_factory, sender, settings.group_chat_id
            )
            async with scheduler:
                await scheduler.start_in_background()

                agent = create_agent(settings)

                async def process_message(job: MessageJob) -> None:
                    async with session_factory() as session:
                        task_service = TaskService(session)
                        member_service = MemberService(session)
                        deps = AgentDeps(
                            task_service=task_service,
                            member_service=member_service,
                        )
                        result = await agent.run(job.body, deps=deps)
                        await sender.send(job.group_id, result.output)

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

    admin_app = create_admin_app(settings, session_factory, None)  # type: ignore[arg-type]  # waha_client created in lifespan
    app.mount("/admin", admin_app)

    return app
