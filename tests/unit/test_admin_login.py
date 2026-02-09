"""Tests for admin login functionality."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from src.core.config import Settings
from src.interface.admin_router import router as admin_router
from src.services.house_config_service import HouseConfig


@pytest.fixture
def client() -> TestClient:
    """Create test client for admin router."""
    test_app = FastAPI()
    test_app.include_router(admin_router)
    return TestClient(test_app)


def test_login_page_renders(client: TestClient) -> None:
    """Test that login page renders correctly with CSRF token."""
    with patch("src.interface.admin_router.settings") as mock_settings:
        mock_settings.admin_password = "test_password"
        mock_settings.secret_key = "test_secret_key"

        response = client.get("/admin/login")

        assert response.status_code == 200
        assert "<h1>Login</h1>" in response.text
        assert "Password" in response.text
        assert 'name="csrf_token"' in response.text
        assert "csrf_token" in response.cookies


def test_login_with_valid_password_redirects(client: TestClient) -> None:
    """Test that valid password redirects to /admin and sets session cookie."""
    with (
        patch("src.interface.admin_router.settings") as mock_settings,
        patch("src.interface.admin_router.csrf_serializer") as mock_csrf_serializer,
    ):
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"
        test_csrf_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-csrf")
        mock_csrf_serializer.dumps = test_csrf_serializer.dumps
        mock_csrf_serializer.loads = test_csrf_serializer.loads

        csrf_token = test_csrf_serializer.dumps("test_csrf_value")

        response = client.post(
            "/admin/login",
            data={"password": "correct_password", "csrf_token": "test_csrf_value"},
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin"
        assert "admin_session" in response.cookies


def test_login_with_invalid_password_shows_error(client: TestClient) -> None:
    """Test that invalid password shows error message."""
    with (
        patch("src.interface.admin_router.settings") as mock_settings,
        patch("src.interface.admin_router.csrf_serializer") as mock_csrf_serializer,
    ):
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"
        test_csrf_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-csrf")
        mock_csrf_serializer.dumps = test_csrf_serializer.dumps
        mock_csrf_serializer.loads = test_csrf_serializer.loads

        csrf_token = test_csrf_serializer.dumps("test_csrf_value")

        response = client.post(
            "/admin/login",
            data={"password": "wrong_password", "csrf_token": "test_csrf_value"},
            cookies={"csrf_token": csrf_token},
        )

        assert response.status_code == 200
        assert "Invalid password" in response.text
        assert "admin_session" not in response.cookies


def test_startup_fails_without_admin_password() -> None:
    """Test that application startup fails when admin_password is missing."""
    settings = Settings(
        openrouter_api_key="test_key",
        admin_password=None,
        secret_key="test_secret",
    )
    with pytest.raises(ValueError, match="Admin password for web interface credential not configured"):
        settings.require_credential("admin_password", "Admin password for web interface")


def test_startup_fails_without_secret_key() -> None:
    """Test that application startup fails when secret_key is missing."""
    settings = Settings(
        openrouter_api_key="test_key",
        admin_password="admin_password",
        secret_key=None,
    )
    with pytest.raises(ValueError, match="Secret key for session signing credential not configured"):
        settings.require_credential("secret_key", "Secret key for session signing")


def test_protected_route_without_session_redirects(client: TestClient) -> None:
    """Test that accessing protected route without session redirects to login."""
    with patch("src.interface.admin_router.settings") as mock_settings:
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"

        response = client.get("/admin/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_protected_route_with_invalid_session_redirects(client: TestClient) -> None:
    """Test that accessing protected route with invalid session redirects to login."""
    with patch("src.interface.admin_router.settings") as mock_settings:
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"

        response = client.get(
            "/admin/",
            cookies={"admin_session": "invalid_token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_protected_route_with_valid_session_succeeds(client: TestClient) -> None:
    """Test that accessing protected route with valid session succeeds."""
    with (
        patch("src.interface.admin_router.settings") as mock_settings,
        patch(
            "src.interface.admin_router.serializer",
            URLSafeTimedSerializer("test_secret_key", salt="admin-session"),
        ),
        patch("src.interface.admin_router.get_house_config_from_service") as mock_get_config,
        patch("src.interface.admin_router.list_records") as mock_list_records,
    ):
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"
        mock_get_config.return_value = HouseConfig(name="TestHouse")
        mock_list_records.return_value = []

        serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-session")
        session_token = serializer.dumps({"authenticated": True})

        client.cookies.set("admin_session", session_token)
        response = client.get("/admin/")

        assert response.status_code == 200
        assert "TestHouse" in response.text


def test_logout_clears_session_and_redirects(client: TestClient) -> None:
    """Test that logout clears session cookie and redirects to login."""
    with patch("src.interface.admin_router.settings") as mock_settings:
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"

        response = client.get("/admin/logout", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        # Cookie should be cleared
        set_cookie = response.headers.get("set-cookie")
        assert set_cookie is not None
        assert "admin_session=" in set_cookie
        # Check cookie is cleared with either max-age=0 or expires in past
        assert "max-age=0" in set_cookie or "expires=" in set_cookie.lower()


def test_login_with_invalid_csrf_token_returns_403(client: TestClient) -> None:
    """Test that invalid CSRF token returns 403 error."""
    with patch("src.interface.admin_router.settings") as mock_settings:
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"

        response = client.post("/admin/login", data={"password": "correct_password", "csrf_token": "invalid_token"})

        assert response.status_code == 403


def test_login_with_missing_csrf_token_returns_403(client: TestClient) -> None:
    """Test that missing CSRF token returns 403 error."""
    with patch("src.interface.admin_router.settings") as mock_settings:
        mock_settings.admin_password = "correct_password"
        mock_settings.secret_key = "test_secret_key"

        response = client.post("/admin/login", data={"password": "correct_password"})

        assert response.status_code == 403
