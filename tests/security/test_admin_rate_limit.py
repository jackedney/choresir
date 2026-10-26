import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from choresir.admin.app import create_admin_app
from choresir.config import Settings


@pytest.fixture
def test_settings():
    return Settings(
        admin_user="admin",
        admin_password="password",
        admin_secret="test_secret",
        waha_webhook_secret="test_webhook_secret",
    )


@pytest.fixture
def mock_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    return async_sessionmaker(engine)


@pytest.mark.anyio
async def test_admin_login_rate_limit(test_settings, mock_session_factory):
    app = create_admin_app(test_settings, mock_session_factory)
    ASGITransport(app=app, client=("192.168.1.1", 12345))

    # We mount it in fastapi so it's under /admin like in real app
    from fastapi import FastAPI

    main_app = FastAPI()
    main_app.mount("/admin", app)
    main_transport = ASGITransport(app=main_app, client=("192.168.1.1", 12345))

    async with AsyncClient(
        transport=main_transport, base_url="http://testserver"
    ) as client:
        # 5 failed login attempts
        for _ in range(5):
            response = await client.post(
                "/admin/login/submit",
                data={"username": "wrong", "password": "wrong"},
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/admin/login?error=1"

        # 6th attempt should be rate limited
        response = await client.post(
            "/admin/login/submit",
            data={"username": "wrong", "password": "wrong"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login?error=ratelimit"

        # Check with different IP, it should not be rate limited
        transport2 = ASGITransport(app=main_app, client=("192.168.1.2", 12345))
        async with AsyncClient(
            transport=transport2, base_url="http://testserver"
        ) as client2:
            response = await client2.post(
                "/admin/login/submit",
                data={"username": "wrong", "password": "wrong"},
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/admin/login?error=1"
