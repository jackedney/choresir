"""Self-registering tool registry for the PydanticAI agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai import Agent


@dataclass
class ToolRegistry:
    """Collects tool functions and bulk-registers them on an agent."""

    _tools: list[Callable] = field(default_factory=list)

    def register(self, fn: Callable) -> Callable:
        """Decorator that adds a function to the registry."""
        self._tools.append(fn)
        return fn

    def apply[D, R](self, agent: Agent[D, R]) -> None:
        """Register all collected tools on the given agent."""
        for tool_fn in self._tools:
            agent.tool(tool_fn)


registry = ToolRegistry()
