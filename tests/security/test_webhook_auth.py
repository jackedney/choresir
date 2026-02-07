from unittest.mock import patch

import pytest

from src.interface.webhook_security import WebhookSecurityResult, validate_webhook_secret, verify_webhook_security


@pytest.mark.asyncio
async def test_validate_webhook_secret_not_configured():
    """Test that validation passes when secret is not configured (backward compatibility)."""
    # Case 1: Header provided, config missing -> Pass
    result = await validate_webhook_secret(received_secret="anything", expected_secret=None)
    assert result.is_valid
    assert result.error_message is None

    # Case 2: Header missing, config missing -> Pass
    result = await validate_webhook_secret(received_secret=None, expected_secret=None)
    assert result.is_valid


@pytest.mark.asyncio
async def test_validate_webhook_secret_missing_header():
    """Test that validation fails when header is missing but secret is configured."""
    result = await validate_webhook_secret(received_secret=None, expected_secret="s3cret")
    assert not result.is_valid
    assert result.error_message == "Missing webhook secret"
    assert result.http_status_code == 401


@pytest.mark.asyncio
async def test_validate_webhook_secret_invalid():
    """Test that validation fails when secret is incorrect."""
    result = await validate_webhook_secret(received_secret="wrong", expected_secret="s3cret")
    assert not result.is_valid
    assert result.error_message == "Invalid webhook secret"
    assert result.http_status_code == 403


@pytest.mark.asyncio
async def test_validate_webhook_secret_valid():
    """Test that validation passes when secrets match."""
    result = await validate_webhook_secret(received_secret="s3cret", expected_secret="s3cret")
    assert result.is_valid


@pytest.mark.asyncio
async def test_verify_webhook_security_integration_failure():
    """Test that verify_webhook_security fails fast on auth failure."""
    # We mock timestamp validator to ensure it's NOT called
    with patch("src.interface.webhook_security.validate_webhook_timestamp") as mock_ts:
        # Test auth failure stops flow
        result = await verify_webhook_security(
            message_id="123",
            timestamp_str="1234567890",
            phone_number="123",
            received_secret="wrong",
            expected_secret="s3cret",
        )
        assert not result.is_valid
        assert result.http_status_code == 403

        # Timestamp validator should NOT be called if auth fails
        mock_ts.assert_not_called()


@pytest.mark.asyncio
async def test_verify_webhook_security_integration_success():
    """Test that verify_webhook_security proceeds when auth passes."""
    # We mock subsequent checks to pass
    with (
        patch("src.interface.webhook_security.validate_webhook_timestamp") as mock_ts,
        patch("src.interface.webhook_security.validate_webhook_nonce") as mock_nonce,
        patch("src.interface.webhook_security.validate_webhook_rate_limit") as mock_rl,
    ):
        success = WebhookSecurityResult(True, None, None)
        mock_ts.return_value = success
        mock_nonce.return_value = success
        mock_rl.return_value = success

        result = await verify_webhook_security(
            message_id="123",
            timestamp_str="1234567890",
            phone_number="123",
            received_secret="s3cret",
            expected_secret="s3cret",
        )
        assert result.is_valid

        # Subsequent checks SHOULD be called
        mock_ts.assert_called_once()
