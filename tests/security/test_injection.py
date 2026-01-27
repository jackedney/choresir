import pytest
from unittest.mock import patch, MagicMock
from src.services.chore_service import get_chores
from src.services.analytics_service import get_overdue_chores
from src.domain.chore import ChoreState

@pytest.mark.asyncio
async def test_get_chores_injection():
    """Verify get_chores is safe against filter injection."""
    # Mock return value to avoid actual DB calls
    mock_records = [{"id": "1", "title": "Test"}]

    # We patch 'src.core.db_client.list_records' where it is defined
    with patch("src.core.db_client.list_records", return_value=mock_records) as mock_list:
        # Malicious input
        malicious_user_id = 'user" || 1=1 || "'

        await get_chores(user_id=malicious_user_id)

        # Verify the call arguments
        assert mock_list.called
        call_kwargs = mock_list.call_args.kwargs
        filter_query = call_kwargs.get("filter_query", "")

        # Check that the malicious input is NOT present as-is (it should be escaped)
        # The expected behavior depends on sanitize_param implementation.
        # sanitize_param('foo"') -> 'foo\"'
        # So 'user" || 1=1 || "' should become 'user\" || 1=1 || \"'
        # And the filter string should contain the escaped version

        # We expect the filter to be constructed safely.
        # If vulnerable: assigned_to = "user" || 1=1 || ""
        # If safe: assigned_to = "user\" || 1=1 || \""

        # We check that the filter query contains the ESCAPED version of the quote
        # escaping " results in \" in the string
        assert '\\"' in filter_query or '\\"' in filter_query.replace("'", '"')

        # Also, check that the raw malicious string structure is NOT present
        # This is a heuristic check
        assert f'assigned_to = "{malicious_user_id}"' not in filter_query

@pytest.mark.asyncio
async def test_get_overdue_chores_injection():
    """Verify get_overdue_chores is safe against filter injection."""
    mock_records = []

    with patch("src.core.db_client.list_records", return_value=mock_records) as mock_list:
        malicious_user_id = 'user" || 1=1 || "'

        await get_overdue_chores(user_id=malicious_user_id)

        assert mock_list.called
        call_kwargs = mock_list.call_args.kwargs
        filter_query = call_kwargs.get("filter_query", "")

        # Similar check as above
        assert '\\"' in filter_query or '\\"' in filter_query.replace("'", '"')
        assert f'assigned_to = "{malicious_user_id}"' not in filter_query
