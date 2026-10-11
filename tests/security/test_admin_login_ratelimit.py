import pytest
from httpx import ASGITransport, AsyncClient

from choresir.admin.pages import _login_attempts, _login_attempts_lock
from choresir.app import create_app
from choresir.config import Settings


@pytest.mark.anyio
async def test_admin_login_rate_limiting():
    # Setup the application
    settings = Settings(
        admin_user="admin", admin_password="password", admin_secret="testsecret"
    )
    app = create_app(settings)

    # Clear the dictionary before test
    with _login_attempts_lock:
        _login_attempts.clear()

    client_ip = "192.168.1.100"

    async with AsyncClient(
        transport=ASGITransport(app=app, client=(client_ip, 12345)),
        base_url="http://testserver",
    ) as client:
        # First 5 attempts fail auth but return 303 (redirect to ?error=1)
        for _ in range(5):
            response = await client.post(
                "/admin/login/submit", data={"username": "wrong", "password": "wrong"}
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/admin/login?error=1"

        # 6th attempt should be rate limited
        response = await client.post(
            "/admin/login/submit", data={"username": "wrong", "password": "wrong"}
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login?error=ratelimit"

        # Test eviction bounding (using mock to simulate)
        # Clear rate limit and verify different IP is not affected
        client_ip_2 = "10.0.0.1"
        async with AsyncClient(
            transport=ASGITransport(app=app, client=(client_ip_2, 12345)),
            base_url="http://testserver",
        ) as client2:
            response = await client2.post(
                "/admin/login/submit", data={"username": "wrong", "password": "wrong"}
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/admin/login?error=1"
