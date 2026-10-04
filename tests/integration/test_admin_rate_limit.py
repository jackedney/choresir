import pytest
from httpx import ASGITransport, AsyncClient

import choresir.admin.pages
from choresir.app import create_app
from choresir.config import Settings


@pytest.fixture(autouse=True)
def reset_rate_limit():
    choresir.admin.pages._login_attempts.clear()
    yield


@pytest.fixture
def mock_app():
    settings = Settings(admin_user="admin", admin_password="password")
    return create_app(settings)


@pytest.mark.anyio
async def test_admin_login_rate_limit(mock_app):
    transport = ASGITransport(app=mock_app, client=("127.0.0.1", 12345))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # First 5 attempts should fail with normal credential error
        for _ in range(5):
            resp = await client.post(
                "/admin/login/submit",
                data={"username": "foo", "password": "bar"},
            )
            assert resp.status_code == 303
            assert resp.headers["location"] == "/admin/login?error=1"

        # 6th attempt should trigger rate limit
        resp = await client.post(
            "/admin/login/submit",
            data={"username": "foo", "password": "bar"},
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/login?error=ratelimit"

        # Verify the login page displays the rate limit error
        resp = await client.get("/admin/login?error=ratelimit")
        assert resp.status_code == 200
        assert b"Too many login attempts" in resp.content
