import pytest
from httpx import ASGITransport, AsyncClient

from choresir.app import create_app
from choresir.config import Settings


@pytest.fixture
def test_settings():
    return Settings(
        admin_user="admin",
        admin_password="password",
        admin_secret="test_secret_for_testing_1234567890",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def app(test_settings):
    return create_app(test_settings)


@pytest.mark.anyio
async def test_admin_login_rate_limit(app):
    from choresir.admin import pages

    pages._login_attempts.clear()

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 1234)),
        base_url="http://testserver",
    ) as client:
        # First 5 attempts should not be rate limited
        for _ in range(5):
            response = await client.post(
                "/admin/login/submit",
                data={"username": "admin", "password": "wrongpassword"},
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/admin/login?error=1"

        # 6th attempt should be rate limited
        response = await client.post(
            "/admin/login/submit",
            data={"username": "admin", "password": "password"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login?error=ratelimit"
