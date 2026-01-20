import httpx
import pytest


@pytest.mark.asyncio
async def test_anonymous_users_access_denied(pocketbase_server, initialized_db):
    """Verify that anonymous users cannot list users."""
    async with httpx.AsyncClient(base_url=pocketbase_server) as client:
        # Try to list users anonymously
        response = await client.get("/api/collections/users/records")

        # Currently this will fail (it will return 200 OK because rules are public)
        # We verify that it SHOULD be 403
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
