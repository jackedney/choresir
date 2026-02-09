"""Tests for startup validation functions."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.main import check_redis_connectivity, check_waha_connectivity, validate_startup_configuration


@pytest.mark.asyncio
async def test_check_waha_connectivity_success() -> None:
    """Test successful WAHA connectivity check."""
    mock_response = Mock()
    mock_response.is_success = True

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        await check_waha_connectivity()


@pytest.mark.asyncio
async def test_check_waha_connectivity_failure() -> None:
    """Test WAHA connectivity check fails on non-200 status."""
    mock_response = Mock()
    mock_response.is_success = False
    mock_response.status_code = 500

    with (
        patch("httpx.AsyncClient") as mock_client,
        pytest.raises(ConnectionError, match="WAHA connectivity check failed"),
    ):
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        await check_waha_connectivity()


@pytest.mark.asyncio
async def test_check_waha_connectivity_with_api_key() -> None:
    """Test WAHA connectivity check sends API key when configured."""
    mock_response = Mock()
    mock_response.is_success = True
    mock_client_context = Mock()
    mock_get = AsyncMock(return_value=mock_response)
    mock_client_context.get = mock_get
    mock_client_context.__aenter__ = AsyncMock(return_value=mock_client_context)
    mock_client_context.__aexit__ = AsyncMock()

    with (
        patch("src.main.settings") as mock_settings,
        patch("httpx.AsyncClient") as mock_client_class,
    ):
        mock_settings.waha_base_url = "http://waha:3000"
        mock_settings.waha_api_key = "test_key"
        mock_client_class.return_value = mock_client_context

        await check_waha_connectivity()

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["X-Api-Key"] == "test_key"


@pytest.mark.asyncio
async def test_check_redis_connectivity_disabled() -> None:
    """Test Redis check when Redis is not configured."""
    mock_redis = Mock()
    mock_redis.is_available = False

    with patch("src.main.redis_client", mock_redis):
        await check_redis_connectivity()


@pytest.mark.asyncio
async def test_check_redis_connectivity_success() -> None:
    """Test successful Redis connectivity check."""
    mock_redis = Mock()
    mock_redis.is_available = True
    mock_redis.ping = AsyncMock(return_value=True)

    with patch("src.main.redis_client", mock_redis):
        await check_redis_connectivity()
        mock_redis.ping.assert_called_once()


@pytest.mark.asyncio
async def test_validate_startup_configuration_missing_credential() -> None:
    """Test validation fails and exits when credential is missing."""

    def mock_require_credential(field: str, name: str) -> str:
        if field == "openrouter_api_key":
            raise ValueError(f"{name} credential not configured")
        return "test_value"

    with (
        patch("src.main.settings") as mock_settings,
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_settings.require_credential.side_effect = mock_require_credential
        await validate_startup_configuration()

    exc = exc_info.value
    assert isinstance(exc, SystemExit)
    assert exc.code == 1


@pytest.mark.asyncio
async def test_validate_startup_configuration_service_unreachable() -> None:
    """Test validation fails and exits when service is unreachable."""

    async def mock_check_waha() -> None:
        raise ConnectionError("WAHA unreachable")

    with (
        patch("src.main.settings") as mock_settings,
        patch("src.main.check_waha_connectivity", side_effect=mock_check_waha),
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_settings.require_credential.return_value = "test_value"
        await validate_startup_configuration()

    exc = exc_info.value
    assert isinstance(exc, SystemExit)
    assert exc.code == 1


@pytest.mark.asyncio
async def test_validate_startup_configuration_all_checks_pass() -> None:
    """Test validation passes when all checks succeed."""
    with (
        patch("src.main.settings") as mock_settings,
        patch("src.main.check_waha_connectivity", new_callable=AsyncMock),
        patch("src.main.check_redis_connectivity", new_callable=AsyncMock),
    ):
        mock_settings.require_credential.return_value = "test_value"
        await validate_startup_configuration()

        mock_settings.require_credential.assert_called_once()
