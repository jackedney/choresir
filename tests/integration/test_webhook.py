"""Integration tests for webhook auth, dedup, and filtering."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from choresir.errors import WebhookAuthError
from choresir.models.job import MessageJob
from choresir.webhook.router import create_webhook_router

_SECRET = "test-secret"


def _sign(body: bytes) -> str:
    return hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _payload(
    msg_id: str = "msg-1",
    from_me: bool = False,
    event: str = "message",
) -> bytes:
    return json.dumps(
        {
            "event": event,
            "payload": {
                "id": msg_id,
                "fromMe": from_me,
                "from": "sender@c.us",
                "to": "group@g.us",
                "body": "Hello",
            },
        }
    ).encode()


@pytest.fixture
async def webhook_client(engine):
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app = FastAPI()

    @app.exception_handler(WebhookAuthError)
    async def _h(request, exc):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    app.include_router(create_webhook_router(sm, _SECRET))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_webhook_missing_signature_returns_401(webhook_client: AsyncClient):
    resp = await webhook_client.post("/webhook", content=_payload())
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_webhook_invalid_signature_returns_401(webhook_client: AsyncClient):
    resp = await webhook_client.post(
        "/webhook",
        content=_payload(),
        headers={"X-WAHA-Signature-256": "bad"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_webhook_valid_message_enqueued(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    body = _payload(msg_id="msg-enqueue")
    resp = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        job = await s.get(MessageJob, "msg-enqueue")
        assert job is not None
        assert job.sender_id == "sender@c.us"


@pytest.mark.anyio
async def test_webhook_duplicate_message_ignored(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    body = _payload(msg_id="msg-dup")
    headers = {"X-WAHA-Signature-256": _sign(body)}
    await webhook_client.post("/webhook", content=body, headers=headers)
    await webhook_client.post("/webhook", content=body, headers=headers)
    async with session_factory() as s:
        rows = (
            await s.execute(select(MessageJob).where(MessageJob.id == "msg-dup"))
        ).all()
        assert len(rows) == 1


@pytest.mark.anyio
async def test_webhook_from_me_ignored(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    body = _payload(msg_id="msg-fm", from_me=True)
    resp = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        assert await s.get(MessageJob, "msg-fm") is None


@pytest.mark.anyio
async def test_webhook_group_message_extracts_participant_as_sender(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """In group messages, 'from' is the group JID and 'participant' is the sender."""
    body = json.dumps(
        {
            "event": "message",
            "payload": {
                "id": "msg-group",
                "fromMe": False,
                "from": "120363XXX@g.us",
                "to": "bot@c.us",
                "participant": "sender@c.us",
                "body": "Hello from group",
            },
        }
    ).encode()
    resp = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        job = await s.get(MessageJob, "msg-group")
        assert job is not None
        assert job.sender_id == "sender@c.us"
        assert job.group_id == "120363XXX@g.us"


@pytest.mark.anyio
async def test_webhook_non_message_event_ignored(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    body = _payload(msg_id="msg-ack", event="ack")
    resp = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        assert await s.get(MessageJob, "msg-ack") is None
