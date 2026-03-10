"""Tests for call_agent_with_retry retry behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from choresir.app import call_agent_with_retry


class TestCallAgentWithRetry:
    @pytest.mark.anyio
    async def test_retries_on_timeout_error(self, agent_deps):
        agent = MagicMock()
        agent.run = AsyncMock(
            side_effect=[
                TimeoutError("Connection timeout"),
                TimeoutError("Connection timeout"),
                MagicMock(output="Success"),
            ]
        )

        result = await call_agent_with_retry(agent, "test message", agent_deps)

        assert result == "Success"
        assert agent.run.call_count == 3

    @pytest.mark.anyio
    async def test_retries_on_httpx_request_error(self, agent_deps):
        agent = MagicMock()
        agent.run = AsyncMock(
            side_effect=[
                httpx.RequestError("Network error"),
                MagicMock(output="Success"),
            ]
        )

        result = await call_agent_with_retry(agent, "test message", agent_deps)

        assert result == "Success"
        assert agent.run.call_count == 2

    @pytest.mark.anyio
    async def test_fails_after_max_attempts(self, agent_deps):
        agent = MagicMock()
        agent.run = AsyncMock(side_effect=TimeoutError("Connection timeout"))

        with pytest.raises(TimeoutError, match="Connection timeout"):
            await call_agent_with_retry(agent, "test message", agent_deps)

        assert agent.run.call_count == 5

    @pytest.mark.anyio
    async def test_no_retry_on_other_exceptions(self, agent_deps):
        agent = MagicMock()
        agent.run = AsyncMock(side_effect=ValueError("Invalid input"))

        with pytest.raises(ValueError, match="Invalid input"):
            await call_agent_with_retry(agent, "test message", agent_deps)

        assert agent.run.call_count == 1

    @pytest.mark.anyio
    async def test_retries_mixed_transient_errors(self, agent_deps):
        agent = MagicMock()
        agent.run = AsyncMock(
            side_effect=[
                TimeoutError("Timeout"),
                httpx.RequestError("Network error"),
                MagicMock(output="Success"),
            ]
        )

        result = await call_agent_with_retry(agent, "test message", agent_deps)

        assert result == "Success"
        assert agent.run.call_count == 3
