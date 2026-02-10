"""Base utilities and dependencies for Pydantic AI agents."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Deps:
    """Dependencies injected into agent RunContext."""

    db: Any
    user_id: str
    user_phone: str
    user_name: str
    user_role: str
    current_time: datetime
