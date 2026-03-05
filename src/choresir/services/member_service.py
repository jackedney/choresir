"""Member registration, onboarding, and query logic."""

from __future__ import annotations

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from choresir.enums import MemberRole, MemberStatus
from choresir.errors import AuthorizationError, NotFoundError
from choresir.models.member import Member


class MemberService:
    """Member lifecycle: registration, onboarding, status, and queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_pending(self, whatsapp_id: str) -> Member:
        """Create a member with PENDING status, using INSERT OR IGNORE for re-joins."""
        stmt = sqlite_insert(Member).values(
            whatsapp_id=whatsapp_id,
            status=MemberStatus.PENDING,
            role=MemberRole.MEMBER,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["whatsapp_id"])
        await self._session.exec(stmt)  # type: ignore[arg-type]
        await self._session.commit()

        return await self.get_by_whatsapp_id(whatsapp_id)

    async def activate(self, whatsapp_id: str, name: str) -> Member:
        """Set name and transition member to ACTIVE status."""
        member = await self.get_by_whatsapp_id(whatsapp_id)
        member.sqlmodel_update({"name": name, "status": MemberStatus.ACTIVE})
        self._session.add(member)
        await self._session.commit()
        await self._session.refresh(member)
        return member

    async def get_by_whatsapp_id(self, whatsapp_id: str) -> Member:
        """Look up a member by WhatsApp ID, raising NotFoundError if absent."""
        result = await self._session.exec(
            select(Member).where(Member.whatsapp_id == whatsapp_id)
        )
        member = result.first()
        if member is None:
            raise NotFoundError("Member", whatsapp_id)
        return member

    async def get_active(self, member_id: int) -> Member:
        """Get a member by ID, raising AuthorizationError if not ACTIVE."""
        member = await self._session.get(Member, member_id)
        if member is None:
            raise NotFoundError("Member", member_id)
        if member.status != MemberStatus.ACTIVE:
            raise AuthorizationError(
                f"Member {member_id} is not active (status={member.status})"
            )
        return member

    async def list_active(self) -> list[Member]:
        """Return only ACTIVE members."""
        result = await self._session.exec(
            select(Member).where(Member.status == MemberStatus.ACTIVE)
        )
        return list(result.all())

    async def list_all(self) -> list[Member]:
        """Return all members regardless of status."""
        result = await self._session.exec(select(Member))
        return list(result.all())

    async def set_role(self, member_id: int, role: MemberRole) -> Member:
        """Update a member's role."""
        member = await self._session.get(Member, member_id)
        if member is None:
            raise NotFoundError("Member", member_id)
        member.sqlmodel_update({"role": role})
        self._session.add(member)
        await self._session.commit()
        await self._session.refresh(member)
        return member
