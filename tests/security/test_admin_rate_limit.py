
import pytest
from httpx import ASGITransport, AsyncClient

import choresir.admin.pages as admin_pages
from choresir.app import create_app
from choresir.config import Settings


@pytest.fixture(autouse=True)
def clear_login_attempts():
    admin_pages._login_attempts.clear()


@pytest.mark.anyio
async def test_admin_login_rate_limit():
    settings = Settings(admin_user="admin", admin_password="password")
    app = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        for _ in range(5):
            res = await ac.post(
                "/admin/login/submit", data={"username": "admin", "password": "wrong"}
            )
            assert res.status_code == 303
            assert res.headers["location"] == "/admin/login?error=1"

        # 6th attempt should be rate limited
        res = await ac.post(
            "/admin/login/submit", data={"username": "admin", "password": "wrong"}
        )
        assert res.status_code == 303
        assert res.headers["location"] == "/admin/login?error=ratelimit"
