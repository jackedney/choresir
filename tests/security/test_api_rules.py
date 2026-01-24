import httpx
import pytest


@pytest.mark.asyncio
async def test_anonymous_users_access_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot list users."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to list users anonymously
        response = await client.get("/api/collections/users/records")

        # Verify that anonymous access is denied
        assert response.status_code == 403, (
            f"Anonymous access to users collection should be denied. Got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_anonymous_create_user_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot create users directly via API."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to create user anonymously
        response = await client.post(
            "/api/collections/users/records",
            json={
                "phone": "+19999999999",
                "password": "1234567890",
                "passwordConfirm": "1234567890",
                "role": "member",
                "status": "pending",
            },
        )
        assert response.status_code == 403, f"Anonymous creation of users should be denied. Got {response.status_code}"


@pytest.mark.asyncio
async def test_anonymous_join_sessions_access_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot list join sessions."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to list join_sessions anonymously
        response = await client.get("/api/collections/join_sessions/records")

        # Verify that anonymous access is denied
        assert response.status_code == 403, (
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
