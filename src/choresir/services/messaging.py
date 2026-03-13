"""Messaging service: protocol and WAHA implementation."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class MessageSender(Protocol):
    """Abstraction for sending messages to a chat."""

    async def send(self, chat_id: str, text: str) -> None: ...


class NullSender:
    """No-op sender for jobs that don't send messages."""

    async def send(self, chat_id: str, text: str) -> None:
        pass


class WAHAClient:
    """Send messages via the WAHA HTTP API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        session: str,
        http: httpx.AsyncClient,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._session = session
        self._http = http

    async def _start_session(self) -> None:
        """Attempt to start the WAHA session."""
        logger.info("WAHA session not running, attempting to start")
        try:
            resp = await self._http.post(
                f"{self._base_url}/api/sessions/{self._session}/start",
                headers={"X-Api-Key": self._api_key},
            )
            resp.raise_for_status()
            logger.info("WAHA session start request succeeded")
        except httpx.HTTPStatusError:
            logger.info("WAHA session start failed (may already be starting)")

    def _is_session_stopped(self, resp: httpx.Response) -> bool:
        """Check if a 422 response indicates the session is stopped."""
        if resp.status_code != 422:
            return False
        try:
            body = resp.json()
            return body.get("status") == "STOPPED"
        except Exception:  # noqa: BLE001
            return False

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError)
        | retry_if_exception_type(httpx.RequestError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=3, max=60),
        reraise=True,
    )
    async def send(self, chat_id: str, text: str) -> None:
        """POST a text message to WAHA's /api/sendText endpoint."""
        resp = await self._http.post(
            f"{self._base_url}/api/sendText",
            json={
                "chatId": chat_id,
                "text": text,
                "session": self._session,
            },
            headers={"X-Api-Key": self._api_key},
        )
        if self._is_session_stopped(resp):
            await self._start_session()
        resp.raise_for_status()
