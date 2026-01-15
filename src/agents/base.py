"""Base utilities and dependencies for Pydantic AI agents."""

from dataclasses import dataclass
from datetime import datetime

from pocketbase import PocketBase


@dataclass
class Deps:
    """Dependencies injected into agent RunContext."""

    db: PocketBase
    user_id: str
    user_phone: str
    user_name: str
    user_role: str
    current_time: datetime
