from unittest.mock import AsyncMock, patch

import pytest

from src.services import verification_service


@pytest.mark.asyncio
async def test_get_personal_stats_injection():
    # Mock db_client.list_records to inspect the filter_query
    with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list_records:
        mock_list_records.return_value = []

        # Also mock personal_chore_service.get_personal_chores since it's called first
        with patch(
            "src.services.personal_chore_service.get_personal_chores", new_callable=AsyncMock
        ) as mock_get_chores:
            mock_get_chores.return_value = []

            # Malicious phone number trying to inject OR condition
            malicious_phone = '"+1234567890" || true || "'

            await verification_service.get_personal_stats(owner_id=malicious_phone)

            # Check the calls to list_records
            # We expect multiple calls. We want to check the one for personal_chore_logs

            calls = mock_list_records.call_args_list
            found_injection = False
            for call in calls:
                kwargs = call.kwargs
                if "collection" in kwargs and kwargs["collection"] == "personal_chore_logs":
                    filter_query = kwargs.get("filter_query", "")
                    # If injection works, the query will look like:
                    # owner_phone = ""+1234567890" || true || "" && ...

                    # If injection is blocked (sanitized), it should look like:
                    # owner_phone = "\"+1234567890\" || true || \"" && ... (or similar escaping)

                    # We check if the injected payload is present "as is" without escaping
                    # sanitize_param typically escapes quotes.

                    # The payload should NOT be present in its raw form which closes the quote
                    if 'owner_phone = ""+1234567890" || true || ""' in filter_query:
                        found_injection = True

            assert not found_injection, "Vulnerability found! The injected payload WAS present in the filter query."
