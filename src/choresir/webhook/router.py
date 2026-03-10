"""FastAPI router for the WAHA webhook endpoint."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from choresir.errors import WebhookAuthError
from choresir.models.job import MessageJob
from choresir.services.member_service import MemberService
from choresir.webhook.auth import validate_webhook


def create_webhook_router(
    session_factory: async_sessionmaker[AsyncSession],
    webhook_secret: str,
) -> APIRouter:
    """Create and return the webhook router with closed-over dependencies."""
    router = APIRouter()

    @router.post("/webhook")
    async def receive_webhook(request: Request) -> dict[str, str]:
        """Receive a WAHA webhook, validate, dedup, and enqueue for processing."""
        body = await request.body()
        signature = request.headers.get("X-Webhook-Hmac") or request.headers.get(
            "X-WAHA-Signature-256", ""
        )

        if not validate_webhook(body, signature, webhook_secret):
            raise WebhookAuthError("Invalid webhook signature")

        payload: dict[str, Any] = json.loads(body)

        # Only process "message" events
        if payload.get("event") != "message":
            # Handle group.v2.join events for auto-registration
            if payload.get("event") == "group.v2.join":
                recipients: list[str] = payload.get("payload", {}).get("recipients", [])
                async with session_factory() as session:
                    member_service = MemberService(session)
                    for whatsapp_id in recipients:
                        await member_service.register_pending(whatsapp_id)
            return {"status": "ok"}

        message = payload.get("payload", {})

        # Filter out messages sent by the bot itself
        if message.get("fromMe", False):
            return {"status": "ok"}

        message_id: str = message.get("id", "")
        from_id: str = message.get("from", "")
        to_id: str = message.get("to", "")
        message_body: str = message.get("body", "")

        # In group messages, "from" is the group JID and the actual
        # sender is in "participant".  For DMs, "from" is the sender.
        if from_id.endswith("@g.us"):
            group_id = from_id
            sender_id = message.get("participant", from_id)
        else:
            sender_id = from_id
            group_id = to_id

        # INSERT OR IGNORE for deduplication via primary key
        stmt = sqlite_insert(MessageJob).values(
            id=message_id,
            sender_id=sender_id,
            group_id=group_id,
            body=message_body,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])

        async with session_factory() as session:
            await session.exec(stmt)
            await session.commit()

        return {"status": "ok"}

    return router
