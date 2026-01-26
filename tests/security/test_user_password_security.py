import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services import user_service

@pytest.mark.asyncio
async def test_request_join_generates_random_password():
    """Verify that request_join generates a random password instead of using a hardcoded one."""

    # Mock settings
    with patch("src.services.user_service.settings") as mock_settings:
        mock_settings.house_code = "HOUSE123"
        mock_settings.house_password = "SECRET_PASSWORD"

        # Mock db_client
        with patch("src.services.user_service.db_client") as mock_db_client:
            # Setup db_client mocks
            mock_db_client.get_first_record = AsyncMock(return_value=None)  # No existing user
            mock_db_client.create_record = AsyncMock(return_value={"id": "new_user_id"})

            # Call request_join
            phone = "+15551234567"
            name = "Test User"
            await user_service.request_join(
                phone=phone,
                name=name,
                house_code="HOUSE123",
                password="SECRET_PASSWORD"
            )

            # Verify create_record was called
            assert mock_db_client.create_record.called

            # Get arguments passed to create_record
            call_args = mock_db_client.create_record.call_args
            assert call_args is not None

            kwargs = call_args.kwargs
            assert "collection" in kwargs
            assert kwargs["collection"] == "users"

            data = kwargs["data"]
            password = data.get("password")
            password_confirm = data.get("passwordConfirm")

            # Verify password properties
            assert password is not None, "Password should not be None"
            assert password_confirm == password, "Password and confirm should match"

            # CRITICAL CHECK: Password should NOT be the hardcoded value
            hardcoded_value = "temp_password_will_be_set_on_activation"
            assert password != hardcoded_value, f"Password should not be hardcoded '{hardcoded_value}'"

            # Verify complexity (length check)
            assert len(password) >= 32, f"Password length should be at least 32, got {len(password)}"
