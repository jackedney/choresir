import time

import pytest
from httpx import ASGITransport, AsyncClient

from choresir.app import create_app
from choresir.config import Settings


@pytest.fixture
def test_app():
    settings = Settings(
        admin_user="admin@test.local",
        admin_password="testpassword123",
        admin_secret="test_secret_key_12345_for_testing",
    )
    return create_app(settings)


@pytest.fixture
def client(test_app):
    transport = ASGITransport(app=test_app, client=("127.0.0.1", 12345))
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def client_another_ip(test_app):
    transport = ASGITransport(app=test_app, client=("127.0.0.2", 12345))
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_admin_login_rate_limit(client, client_another_ip):
    # Clear the global dictionary before the test to ensure test isolation
    import choresir.admin.pages

    choresir.admin.pages._login_attempts.clear()

    login_url = "/admin/login/submit"
    form_data = {"username": "admin@test.local", "password": "wrongpassword"}

    # 5 attempts should return normal error
    for _i in range(5):
        response = await client.post(login_url, data=form_data)
        assert response.status_code == 303
        assert response.headers["Location"] == "/admin/login?error=1"

    # 6th attempt should hit rate limit
    response = await client.post(login_url, data=form_data)
    assert response.status_code == 303
    assert response.headers["Location"] == "/admin/login?error=ratelimit"

    # Check that another IP is not rate limited
    response = await client_another_ip.post(login_url, data=form_data)
    assert response.status_code == 303
    assert response.headers["Location"] == "/admin/login?error=1"


@pytest.mark.anyio
async def test_admin_login_rate_limit_eviction(client):
    import choresir.admin.pages

    choresir.admin.pages._login_attempts.clear()

    # Simulate a full dictionary
    for i in range(choresir.admin.pages.MAX_LOGIN_ATTEMPTS_DICT_SIZE):
        choresir.admin.pages._login_attempts[f"10.0.0.{i}"] = [time.monotonic()]

    # Verify dictionary size
    assert (
        len(choresir.admin.pages._login_attempts)
        == choresir.admin.pages.MAX_LOGIN_ATTEMPTS_DICT_SIZE
    )

    login_url = "/admin/login/submit"
    form_data = {"username": "admin@test.local", "password": "wrongpassword"}

    # This attempt should cause eviction of the oldest entry and succeed without rate limit
    response = await client.post(login_url, data=form_data)

    assert response.status_code == 303
    assert response.headers["Location"] == "/admin/login?error=1"

    # Size should be bounded to MAX_LOGIN_ATTEMPTS_DICT_SIZE
    assert (
        len(choresir.admin.pages._login_attempts)
        == choresir.admin.pages.MAX_LOGIN_ATTEMPTS_DICT_SIZE
    )
