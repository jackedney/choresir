from unittest.mock import AsyncMock, patch

import pytest

from src.services import user_service


@pytest.mark.asyncio
async def test_request_join_uses_strong_password():
    # Arrange
    phone = "+1234567890"
    name = "Test User"
    house_code = "TEST_CODE"
    password = "TEST_PASS"

    # Mock settings in user_service
    with patch("src.services.user_service.settings") as mock_settings:
        mock_settings.house_code = house_code
        mock_settings.house_password = password

        # Mock db_client
        with patch("src.services.user_service.db_client") as mock_db_client:
            mock_db_client.get_first_record = AsyncMock(return_value=None)
            mock_db_client.create_record = AsyncMock(return_value={"id": "user123"})

            # Act
            await user_service.request_join(phone=phone, name=name, house_code=house_code, password=password)

            # Assert
            # Check what arguments were passed to create_record
            call_args = mock_db_client.create_record.call_args
            assert call_args is not None
            _, kwargs = call_args
            data = kwargs["data"]

            # This should fail if the vulnerability exists
            # The current code uses "temp_password_will_be_set_on_activation"
            assert data["password"] != "temp_password_will_be_set_on_activation", "Password is predictable!"
            assert len(data["password"]) >= 16, "Password is too short!"
