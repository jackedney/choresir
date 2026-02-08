import httpx
import pytest


@pytest.mark.asyncio
async def test_anonymous_members_access_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot list members."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to list members anonymously
        response = await client.get("/api/collections/members/records")

        # Verify that anonymous access is denied
        assert response.status_code == 403, (
            f"Anonymous access to members collection should be denied. Got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_anonymous_create_member_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot create members directly via API."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to create member anonymously
        response = await client.post(
            "/api/collections/members/records",
            json={
                "phone": "+19999999999",
                "role": "member",
                "status": "pending",
            },
        )
        assert response.status_code == 403, (
            f"Anonymous creation of members should be denied. Got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_anonymous_join_sessions_access_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot list join sessions."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to list join_sessions anonymously
        response = await client.get("/api/collections/join_sessions/records")

        # Verify that anonymous access is denied.
        # Accept 403 (forbidden) or 404 (collection doesn't exist yet) - both prevent data access.
        assert response.status_code in (403, 404), (
            f"Anonymous access to join_sessions collection should be denied. Got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_anonymous_personal_chores_access_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot list personal chores."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to list personal_chores anonymously
        response = await client.get("/api/collections/personal_chores/records")

        # Verify that anonymous access is denied
        assert response.status_code == 403, (
            f"Anonymous access to personal_chores collection should be denied. Got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_anonymous_personal_chore_logs_access_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot list personal chore logs."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to list personal_chore_logs anonymously
        response = await client.get("/api/collections/personal_chore_logs/records")

        # Verify that anonymous access is denied
        assert response.status_code == 403, (
            f"Anonymous access to personal_chore_logs collection should be denied. Got {response.status_code}"
        )
