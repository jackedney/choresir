"""Base utilities and dependencies for Pydantic AI agents."""

from dataclasses import dataclass
from datetime import datetime

from src.core.db_client import _DBClient


@dataclass
class Deps:
    """Dependencies injected into agent RunContext."""

    db: _DBClient
    user_id: str
    user_phone: str
    user_name: str
    user_role: str
    current_time: datetime
