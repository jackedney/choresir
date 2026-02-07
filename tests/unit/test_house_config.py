"""Tests for house configuration functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from src.interface.admin_router import require_auth, router as admin_router
from src.services.house_config_service import HouseConfig


@pytest.fixture
def client() -> TestClient:
    """Create test client for admin router."""
    test_app = FastAPI()
    test_app.include_router(admin_router)
    return TestClient(test_app)


def assert_redirect_to_login(exc: BaseException) -> None:
    """Assert that an exception is an HTTPException redirecting to login."""
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 303
    assert exc.headers is not None
    assert exc.headers["Location"] == "/admin/login"


def get_test_session_token(secret_key: str) -> str:
    """Create a valid session token for testing."""
    serializer = URLSafeTimedSerializer(secret_key, salt="admin-session")
    return serializer.dumps({"authenticated": True})


def test_house_config_page_renders_without_existing_config(client: TestClient) -> None:
    """Test that house config page renders when no config exists."""
    test_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-session")
    session_token = get_test_session_token("test_secret_key")
    client.cookies.set("admin_session", session_token)

    mock_get_first_record = AsyncMock(return_value=None)

    mock_get_config = AsyncMock(return_value=HouseConfig(name="DefaultHouse", password="", code=""))

    with (
        patch("src.interface.admin_router.settings") as mock_settings,
        patch("src.interface.admin_router.serializer", test_serializer),
        patch("src.interface.admin_router.get_first_record", mock_get_first_record),
        patch("src.interface.admin_router.get_house_config_from_service", mock_get_config),
    ):
        mock_settings.admin_password = "test_password"
        mock_settings.secret_key = "test_secret_key"
        mock_settings.house_name = None
        mock_settings.house_code = None

        response = client.get("/admin/house")

        assert response.status_code == 200
        assert "<h1>Settings</h1>" in response.text


def test_house_config_page_renders_with_existing_config(client: TestClient) -> None:
    """Test that house config page renders with existing config."""
    test_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-session")
    session_token = get_test_session_token("test_secret_key")
    client.cookies.set("admin_session", session_token)

    existing_config = {
        "id": "test_id",
        "name": "TestHouse",
        "code": "TEST123",
        "password": "stored_password",
    }

    mock_get_first_record = AsyncMock(return_value=existing_config)

    with (
        patch("src.interface.admin_router.settings") as mock_settings,
        patch("src.interface.admin_router.serializer", test_serializer),
        patch("src.interface.admin_router.get_first_record", mock_get_first_record),
    ):
        mock_settings.admin_password = "test_password"
        mock_settings.secret_key = "test_secret_key"
        mock_settings.house_name = None
        mock_settings.house_code = None

        response = client.get("/admin/house")

        assert response.status_code == 200
        assert "<h1>Settings</h1>" in response.text
        assert "TestHouse" in response.text
        assert "TEST123" in response.text
        assert "stored_password" not in response.text


@pytest.mark.asyncio
async def test_require_auth_redirects_without_cookie() -> None:
    """Test that require_auth redirects to login when no session cookie is present."""
    mock_request = MagicMock()
    mock_request.cookies.get.return_value = None
    mock_request.url.path = "/admin/house"

    with pytest.raises(HTTPException) as exc_info:
        await require_auth(mock_request)

    assert_redirect_to_login(exc_info.value)


@pytest.mark.asyncio
async def test_require_auth_redirects_with_invalid_session() -> None:
    """Test that require_auth redirects to login with invalid/tampered session."""
    test_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-session")
    # Create a token with a different key to simulate tampering
    bad_serializer = URLSafeTimedSerializer("wrong_key", salt="admin-session")
    bad_token = bad_serializer.dumps({"authenticated": True})

    mock_request = MagicMock()
    mock_request.cookies.get.return_value = bad_token
    mock_request.url.path = "/admin/house"

    with (
        patch("src.interface.admin_router.serializer", test_serializer),
        pytest.raises(HTTPException) as exc_info,
    ):
        await require_auth(mock_request)

    assert_redirect_to_login(exc_info.value)


@pytest.mark.asyncio
async def test_require_auth_redirects_with_unauthenticated_session() -> None:
    """Test that require_auth redirects when session has authenticated=False."""
    test_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-session")
    # Create a valid token but with authenticated=False
    token = test_serializer.dumps({"authenticated": False})

    mock_request = MagicMock()
    mock_request.cookies.get.return_value = token
    mock_request.url.path = "/admin/house"

    with (
        patch("src.interface.admin_router.serializer", test_serializer),
        pytest.raises(HTTPException) as exc_info,
    ):
        await require_auth(mock_request)

    assert_redirect_to_login(exc_info.value)


@pytest.mark.asyncio
async def test_require_auth_passes_with_valid_session() -> None:
    """Test that require_auth allows access with a valid authenticated session."""
    test_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-session")
    token = test_serializer.dumps({"authenticated": True})

    mock_request = MagicMock()
    mock_request.cookies.get.return_value = token
    mock_request.url.path = "/admin/house"

    with patch("src.interface.admin_router.serializer", test_serializer):
        # Should not raise - just returns None
        result = await require_auth(mock_request)
        assert result is None
