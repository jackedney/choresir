from unittest.mock import AsyncMock

import pytest

from src.core import db_client
from src.services import chore_service, personal_verification_service, robin_hood_service


@pytest.fixture
def capture_db_queries(monkeypatch):
    """Mocks db_client functions to capture query parameters."""
    mock_list = AsyncMock(return_value=[])
    mock_get_first = AsyncMock(return_value=None)

    monkeypatch.setattr("src.core.db_client.list_records", mock_list)
    monkeypatch.setattr("src.core.db_client.get_first_record", mock_get_first)

    return mock_list, mock_get_first

@pytest.mark.asyncio
class TestFilterInjection:
    async def test_sanitize_param_escapes_quotes(self):
        """Verify sanitize_param correctly escapes double quotes."""
        malicious_input = 'foo" || true || "'
        sanitized = db_client.sanitize_param(malicious_input)

        # Expected: foo\" || true || \"
        # Because sanitize_param uses json.dumps which escapes quotes with backslash
        assert sanitized == r'foo\" || true || \"'

        # Verify it creates a safe query when embedded
        query = f'field = "{sanitized}"'
        assert query == r'field = "foo\" || true || \""'

    async def test_chore_service_get_chores_injection(self, capture_db_queries):
        """Test SQL injection prevention in get_chores."""
        mock_list, _ = capture_db_queries

        malicious_user_id = 'user1" || true || "'

        await chore_service.get_chores(user_id=malicious_user_id)

        # Check the call args
        call_args = mock_list.call_args
        assert call_args is not None
        kwargs = call_args.kwargs
        filter_query = kwargs.get("filter_query", "")

        # We assert the SAFE behavior. This test should FAIL before the fix.
        expected_part = r'assigned_to = "user1\" || true || \""'
        assert expected_part in filter_query, f"Filter query was not sanitized: {filter_query}"

    async def test_robin_hood_service_takeover_injection(self, capture_db_queries):
        """Test SQL injection prevention in robin_hood_service."""
        mock_list, _ = capture_db_queries

        malicious_user_id = 'user1" || true || "'

        await robin_hood_service.get_weekly_takeover_count(user_id=malicious_user_id)

        call_args = mock_list.call_args
        assert call_args is not None
        filter_query = call_args.kwargs.get("filter_query", "")

        expected_part = r'user_id = "user1\" || true || \""'
        assert expected_part in filter_query, f"Filter query was not sanitized: {filter_query}"

    async def test_personal_verification_stats_injection(self, capture_db_queries):
        """Test SQL injection prevention in get_personal_stats."""
        mock_list, _ = capture_db_queries

        malicious_phone = '+1555" || true || "'

        # We need to mock get_personal_chores too since it calls db_client.list_records
        # But we want to test the db calls made by get_personal_stats itself
        # Actually get_personal_stats calls get_personal_chores which calls db_client
        # Then it calls db_client directly for completions and pending

        await personal_verification_service.get_personal_stats(owner_phone=malicious_phone)

        # list_records is called 3 times:
        # 1. get_personal_chores (ACTIVE)
        # 2. completions
        # 3. pending verifications

        calls = mock_list.call_args_list
        assert len(calls) >= 3

        # Check the completions query (should be the 2nd call usually)
        # We iterate to find the one with completion filter
        found = False
        for call in calls:
            filter_query = call.kwargs.get("filter_query", "")
            if 'verification_status = "SELF_VERIFIED"' in filter_query:
                # This is the completions query
                expected_part = r'owner_phone = "+1555\" || true || \""'
                assert expected_part in filter_query, f"Filter query was not sanitized: {filter_query}"
                found = True
                break

        assert found, "Completions query not found"
