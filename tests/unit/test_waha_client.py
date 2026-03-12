"""Tests for WAHAClient session recovery behavior."""

from __future__ import annotations

import httpx
import pytest
from respx import MockRouter

from choresir.services.messaging import WAHAClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


WAHA_URL = "http://waha:3000"


@pytest.fixture
async def http():
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def client(http: httpx.AsyncClient) -> WAHAClient:
    return WAHAClient(WAHA_URL, "test-key", "default", http)


class TestSessionRecovery:
    @pytest.mark.anyio
    async def test_starts_session_on_422_stopped(
        self, client: WAHAClient, respx_mock: MockRouter
    ):
        """On 422 STOPPED, start session then retry."""
        respx_mock.post(f"{WAHA_URL}/api/sendText").mock(
            side_effect=[
                httpx.Response(422, json={"status": "STOPPED"}),
                httpx.Response(200, json={"id": "msg1"}),
            ]
        )
        respx_mock.post(f"{WAHA_URL}/api/sessions/default/start").mock(
            return_value=httpx.Response(200, json={"status": "WORKING"})
        )

        await client.send("group@g.us", "hello")

        assert respx_mock.calls.call_count == 3  # send, start, send

    @pytest.mark.anyio
    async def test_no_session_start_on_success(
        self, client: WAHAClient, respx_mock: MockRouter
    ):
        """Successful sends should not trigger session start."""
        respx_mock.post(f"{WAHA_URL}/api/sendText").mock(
            return_value=httpx.Response(200, json={"id": "msg1"})
        )

        await client.send("group@g.us", "hello")

        assert respx_mock.calls.call_count == 1

    @pytest.mark.anyio
    async def test_no_session_start_on_other_422(
        self, client: WAHAClient, respx_mock: MockRouter
    ):
        """A 422 without STOPPED status should not trigger session start."""
        respx_mock.post(f"{WAHA_URL}/api/sendText").mock(
            return_value=httpx.Response(422, json={"status": "SCAN_QR_CODE"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.send("group@g.us", "hello")

        start_calls = [
            c for c in respx_mock.calls if "/sessions/" in str(c.request.url)
        ]
        assert len(start_calls) == 0

    @pytest.mark.anyio
    async def test_session_start_failure_still_retries_send(
        self, client: WAHAClient, respx_mock: MockRouter
    ):
        """Even if session start fails, send should still retry."""
        respx_mock.post(f"{WAHA_URL}/api/sendText").mock(
            side_effect=[
                httpx.Response(422, json={"status": "STOPPED"}),
                httpx.Response(200, json={"id": "msg1"}),
            ]
        )
        respx_mock.post(f"{WAHA_URL}/api/sessions/default/start").mock(
            return_value=httpx.Response(500, json={"error": "internal"})
        )

        await client.send("group@g.us", "hello")

        assert respx_mock.calls.call_count == 3


class TestIsSessionStopped:
    @pytest.fixture
    def waha(self) -> WAHAClient:
        http = httpx.AsyncClient()
        return WAHAClient(WAHA_URL, "test-key", "default", http)

    def test_detects_stopped_status(self, waha: WAHAClient):
        resp = httpx.Response(422, json={"status": "STOPPED"})
        assert waha._is_session_stopped(resp) is True

    def test_ignores_other_422(self, waha: WAHAClient):
        resp = httpx.Response(422, json={"status": "SCAN_QR_CODE"})
        assert waha._is_session_stopped(resp) is False

    def test_ignores_non_422(self, waha: WAHAClient):
        resp = httpx.Response(500, json={"status": "STOPPED"})
        assert waha._is_session_stopped(resp) is False

    def test_handles_non_json_body(self, waha: WAHAClient):
        resp = httpx.Response(422, text="not json")
        assert waha._is_session_stopped(resp) is False
