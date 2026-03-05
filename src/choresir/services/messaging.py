"""Messaging service: protocol and WAHA implementation."""

from __future__ import annotations

from typing import Protocol

import httpx


class MessageSender(Protocol):
    """Abstraction for sending messages to a chat."""

    async def send(self, chat_id: str, text: str) -> None: ...


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
        resp.raise_for_status()
