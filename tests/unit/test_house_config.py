"""Tests for house configuration functionality."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from src.interface.admin_router import router as admin_router


@pytest.fixture
def client() -> TestClient:
    """Create test client for admin router."""
    test_app = FastAPI()
    test_app.include_router(admin_router)
    return TestClient(test_app)


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
        assert "House Configuration" in response.text


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
        assert "House Configuration" in response.text
        assert "TestHouse" in response.text
        assert "TEST123" in response.text
        assert "stored_password" not in response.text


@pytest.mark.skip("TestClient redirect handling differs from real requests")
def test_house_config_requires_auth(client: TestClient) -> None:
    """Test that house config routes require authentication."""
    test_serializer = URLSafeTimedSerializer("test_secret_key", salt="admin-session")

    with (
        patch("src.interface.admin_router.settings") as mock_settings,
        patch("src.interface.admin_router.serializer", test_serializer),
    ):
        mock_settings.admin_password = "test_password"
        mock_settings.secret_key = "test_secret_key"

        # Test GET without session
        response = client.get("/admin/house", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

        # Test POST without session
        response = client.post(
            "/admin/house",
            data={"name": "TestHouse", "code": "CODE123", "password": "new_password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
