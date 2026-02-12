"""Onboarding tools for the choresir agent."""

from pydantic_ai import Agent

from src.agents.base import Deps


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent. No onboarding tools needed - members are auto-approved by being in the group."""
