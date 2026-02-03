from unittest.mock import AsyncMock, patch

import pytest

from src.services import analytics_service, chore_service


@pytest.mark.asyncio
async def test_get_chores_injection():
    # Mock db_client.list_records
    with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []

        # malicious user_id containing filter injection payload
        malicious_user_id = 'user1" || true || "'

        await chore_service.get_chores(user_id=malicious_user_id)

        # Check the call arguments
        call_args = mock_list.call_args
        _, kwargs = call_args
        filter_query = kwargs.get("filter_query")

        assert '\\"' in filter_query or "||" not in filter_query, "Filter query appears vulnerable to injection!"


@pytest.mark.asyncio
async def test_analytics_injection():
    # Mock db_client.list_records
    with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list:
        # Setup side_effect to return pending chores so the loop runs
        async def list_side_effect(*args, **kwargs):
            collection = kwargs.get("collection")
            filter_query = kwargs.get("filter_query", "")

            # Return pending chores to populate pending_chore_ids
            if collection == "chores" and "PENDING_VERIFICATION" in filter_query:
                return [{"id": "chore1"}, {"id": "chore2"}]

            return []

        mock_list.side_effect = list_side_effect

        # malicious user_id containing filter injection payload
        malicious_user_id = 'user1" || true || "'

        # Mock get_record for user check
        with patch("src.core.db_client.get_record", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "user1", "name": "User 1"}

            # This calls get_user_statistics which uses user_id in filters
            try:
                await analytics_service.get_user_statistics(user_id=malicious_user_id)
            except Exception:
                # We expect failures due to mocks not returning everything needed for full execution
                # but we only care about the calls to list_records being made
                pass

            # Check calls to list_records
            found_injection = False
            for call in mock_list.mock_calls:
                _, kwargs = call.args, call.kwargs
                filter_query = kwargs.get("filter_query", "")

                # We are looking for the call where user_id is used.
                # Expected vulnerable query: user_id = "user1" || true || "" ...
                if "user_id =" in filter_query and malicious_user_id in filter_query:
                    # Check if it was NOT sanitized (i.e., quotes are not escaped)
                    if '\\"' not in filter_query:
                        if "||" in filter_query and "true" in filter_query:
                            found_injection = True

            assert not found_injection, "Analytics service vulnerable to injection!"
