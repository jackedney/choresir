import pytest
from unittest.mock import AsyncMock, patch
from src.services import analytics_service, robin_hood_service
from src.core.db_client import sanitize_param

@pytest.mark.asyncio
async def test_get_user_statistics_injection():
    """Test that get_user_statistics sanitizes user_id in filter queries."""
    with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list_records, \
         patch("src.core.db_client.get_record", new_callable=AsyncMock) as mock_get_record, \
         patch("src.services.analytics_service.get_leaderboard", new_callable=AsyncMock) as mock_get_leaderboard:

        # Mock user existence check
        mock_get_record.return_value = {"id": "user123", "name": "Test User"}
        mock_get_leaderboard.return_value = []

        # Setup mock for list_records side effect
        async def list_records_side_effect(*args, **kwargs):
            collection = kwargs.get("collection")
            if collection == "chores":
                # Return one pending chore to trigger the claims query
                return [{"id": "chore1", "current_state": "PENDING_VERIFICATION"}]
            if collection == "logs":
                return []
            return []

        mock_list_records.side_effect = list_records_side_effect

        # Malicious user_id containing filter injection payload
        malicious_user_id = 'attacker" || true || "'
        # The expected sanitized version should have escaped quotes: attacker\" || true || \"
        expected_sanitized = 'attacker\\" || true || \\"'

        await analytics_service.get_user_statistics(user_id=malicious_user_id)

        # Check if list_records was called with sanitized user_id
        # We look for calls to list_records querying 'logs'
        claims_query_found = False
        for call in mock_list_records.call_args_list:
            filter_query = call.kwargs.get("filter_query", "")
            if 'action = "claimed_completion"' in filter_query:
                claims_query_found = True

                # It should contain the SANITIZED user_id
                # Note: We check that the substring matches the sanitized version
                assert f'user_id = "{expected_sanitized}"' in filter_query, \
                    f"Filter query should contain sanitized user_id. Got: {filter_query}"

                # Double check: it should NOT contain the raw malicious string in a way that breaks out
                # Ideally, checking for sanitized version is enough, but let's be explicit
                # If we injected successfully, the query would look like: user_id = "attacker" || true || "" ...
                # If sanitized, it looks like: user_id = "attacker\" || true || \"" ...

        assert claims_query_found, "Did not find the claims query call to list_records"

@pytest.mark.asyncio
async def test_get_overdue_chores_injection():
    """Test that get_overdue_chores sanitizes user_id."""
    with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list_records:
        malicious_user_id = 'attacker" || true || "'
        expected_sanitized = 'attacker\\" || true || \\"'

        await analytics_service.get_overdue_chores(user_id=malicious_user_id)

        call = mock_list_records.call_args
        filter_query = call.kwargs.get("filter_query", "")

        assert f'assigned_to = "{expected_sanitized}"' in filter_query, \
            f"Filter query should contain sanitized user_id. Got: {filter_query}"

@pytest.mark.asyncio
async def test_get_weekly_takeover_count_injection():
    """Test that get_weekly_takeover_count sanitizes user_id."""
    with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list_records:
        malicious_user_id = 'attacker" || true || "'
        expected_sanitized = 'attacker\\" || true || \\"'

        await robin_hood_service.get_weekly_takeover_count(user_id=malicious_user_id)

        call = mock_list_records.call_args
        filter_query = call.kwargs.get("filter_query", "")

        assert f'user_id = "{expected_sanitized}"' in filter_query, \
            f"Filter query should contain sanitized user_id. Got: {filter_query}"

@pytest.mark.asyncio
async def test_increment_weekly_takeover_count_injection():
    """Test that increment_weekly_takeover_count sanitizes user_id."""
    with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list_records, \
         patch("src.core.db_client.create_record", new_callable=AsyncMock) as mock_create:

        malicious_user_id = 'attacker" || true || "'
        expected_sanitized = 'attacker\\" || true || \\"'

        mock_list_records.return_value = [] # Simulate no existing record

        await robin_hood_service.increment_weekly_takeover_count(user_id=malicious_user_id)

        # Check list_records call (it checks existence first)
        call = mock_list_records.call_args
        filter_query = call.kwargs.get("filter_query", "")

        assert f'user_id = "{expected_sanitized}"' in filter_query, \
            f"Filter query should contain sanitized user_id. Got: {filter_query}"
