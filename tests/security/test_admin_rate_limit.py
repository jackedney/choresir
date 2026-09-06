import pytest
import time
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from choresir.admin.app import create_admin_app
from choresir.admin.pages import _login_attempts, _login_lock
from choresir.config import Settings


@pytest.fixture
def test_settings():
    return Settings(
        admin_user="admin@test.local",
        admin_password="testpassword123",
        admin_secret="test_secret_for_sessions",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def session_factory(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def test_app(test_settings, session_factory):
    app = FastAPI()
    admin_app = create_admin_app(
        settings=test_settings, session_factory=session_factory
    )
    app.mount("/admin", admin_app)
    return app


@pytest.fixture(autouse=True)
def clear_rate_limit():
    with _login_lock:
        _login_attempts.clear()
    yield
    with _login_lock:
        _login_attempts.clear()


@pytest.mark.anyio
async def test_admin_login_rate_limit(test_app):
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as client:
        # 5 failed attempts
        for _ in range(5):
            response = await client.post(
                "/admin/login/submit",
                data={"username": "wronguser", "password": "wrongpassword"},
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/admin/login?error=1"

        # 6th attempt should be rate limited
        response = await client.post(
            "/admin/login/submit",
            data={"username": "wronguser", "password": "wrongpassword"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login?error=ratelimit"


@pytest.mark.anyio
async def test_admin_login_successful_login_resets_rate_limit(test_app, test_settings):
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as client:
        # 4 failed attempts
        for _ in range(4):
            response = await client.post(
                "/admin/login/submit",
                data={"username": "wronguser", "password": "wrongpassword"},
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/admin/login?error=1"

        # 1 successful attempt
        response = await client.post(
            "/admin/login/submit",
            data={
                "username": test_settings.admin_user,
                "password": test_settings.admin_password,
            },
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"

        # Another failed attempt should now be allowed (not rate limited)
        response = await client.post(
            "/admin/login/submit",
            data={"username": "wronguser", "password": "wrongpassword"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login?error=1"


@pytest.mark.anyio
async def test_admin_login_rate_limit_bounds_dict_size(test_app):
    from choresir.admin.pages import MAX_TRACKED_IPS

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as client:
        # Fill the dictionary exactly to the limit
        with _login_lock:
            for i in range(MAX_TRACKED_IPS):
                _login_attempts[f"ip{i}"] = [time.monotonic()]

            assert len(_login_attempts) == MAX_TRACKED_IPS
            assert "ip0" in _login_attempts

        # One more attempt from a new IP should evict the oldest
        response = await client.post(
            "/admin/login/submit",
            data={"username": "wronguser", "password": "wrongpassword"},
            headers={"x-forwarded-for": "new_ip"},
        )
        assert response.status_code == 303

        with _login_lock:
            assert len(_login_attempts) == MAX_TRACKED_IPS
            assert "ip0" not in _login_attempts
