"""Integration tests for the webhook endpoint (auth, dedup, filtering)."""

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

from choresir.errors import WebhookAuthError
from choresir.models.job import MessageJob
from choresir.webhook.router import create_webhook_router


def _sign_payload(body: bytes, secret: str) -> str:
    """Generate a valid HMAC-SHA256 signature for the given body."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


_SECRET = "test-secret"


def _make_message_payload(
    message_id: str = "msg-1",
    from_me: bool = False,
    event: str = "message",
    sender: str = "sender@c.us",
    group: str = "group@g.us",
    body: str = "Hello",
) -> bytes:
    """Build a WAHA webhook JSON payload as bytes."""
    payload = {
        "event": event,
        "payload": {
            "id": message_id,
            "fromMe": from_me,
            "from": sender,
            "to": group,
            "body": body,
        },
    }
    return json.dumps(payload).encode()


@pytest.fixture
async def webhook_client(engine):
    """Create an AsyncClient wired to a minimal app with only the webhook router."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    router = create_webhook_router(sm, _SECRET)

    app = FastAPI()

    @app.exception_handler(WebhookAuthError)
    async def _auth_handler(request, exc):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def session_factory(engine):
    """Provide a session factory bound to the in-memory engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


# -- Auth tests ----------------------------------------------------------------


@pytest.mark.anyio
async def test_webhook_missing_signature_returns_401(webhook_client: AsyncClient):
    """A request with no signature header is rejected."""
    body = _make_message_payload()
    response = await webhook_client.post("/webhook", content=body)

    assert response.status_code == 401


@pytest.mark.anyio
async def test_webhook_invalid_signature_returns_401(webhook_client: AsyncClient):
    """A request with a wrong signature is rejected."""
    body = _make_message_payload()
    response = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": "bad-signature"},
    )

    assert response.status_code == 401


# -- Happy path ----------------------------------------------------------------


@pytest.mark.anyio
async def test_webhook_valid_message_enqueued(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """A properly signed message event creates a job in the DB."""
    body = _make_message_payload(message_id="msg-enqueue")
    sig = _sign_payload(body, _SECRET)

    response = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": sig},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    async with session_factory() as session:
        job = await session.get(MessageJob, "msg-enqueue")
        assert job is not None
        assert job.sender_id == "sender@c.us"
        assert job.body == "Hello"


# -- Dedup ---------------------------------------------------------------------


@pytest.mark.anyio
async def test_webhook_duplicate_message_ignored(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """Sending the same message ID twice creates only one job row."""
    body = _make_message_payload(message_id="msg-dup")
    sig = _sign_payload(body, _SECRET)
    headers = {"X-WAHA-Signature-256": sig}

    await webhook_client.post("/webhook", content=body, headers=headers)
    await webhook_client.post("/webhook", content=body, headers=headers)

    async with session_factory() as session:
        result = await session.execute(
            select(MessageJob).where(MessageJob.id == "msg-dup")
        )
        jobs = result.all()
        assert len(jobs) == 1


# -- Filtering -----------------------------------------------------------------


@pytest.mark.anyio
async def test_webhook_from_me_ignored(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """Messages with fromMe=true are acknowledged but not enqueued."""
    body = _make_message_payload(message_id="msg-from-me", from_me=True)
    sig = _sign_payload(body, _SECRET)

    response = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": sig},
    )

    assert response.status_code == 200

    async with session_factory() as session:
        job = await session.get(MessageJob, "msg-from-me")
        assert job is None


@pytest.mark.anyio
async def test_webhook_non_message_event_ignored(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """Non-message events (e.g., 'ack') are acknowledged but not enqueued."""
    body = _make_message_payload(message_id="msg-ack", event="ack")
    sig = _sign_payload(body, _SECRET)

    response = await webhook_client.post(
        "/webhook",
        content=body,
        headers={"X-WAHA-Signature-256": sig},
    )

    assert response.status_code == 200

    async with session_factory() as session:
        job = await session.get(MessageJob, "msg-ack")
        assert job is None
