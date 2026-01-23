import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.core.db_client import sanitize_param
from src.services import chore_service, analytics_service
from src.domain.chore import ChoreState

class TestInjection:
    def test_sanitize_param(self):
        # Basic check
        assert sanitize_param('test') == 'test'
        # Injection attempt (quotes)
        assert sanitize_param('test" OR "1"="1') == 'test\\" OR \\"1\\"=\\"1'
        # Injection attempt (backslashes)
        # Input: test\
        # json.dumps: "test\\"
        # Stripped: test\\
        assert sanitize_param('test\\') == 'test\\\\'

    @pytest.mark.asyncio
    async def test_get_chores_sanitization(self):
        with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            # Attack vector
            malicious_user_id = 'user" || true || "'

            await chore_service.get_chores(user_id=malicious_user_id)

            # Verify sanitization
            call_args = mock_list.call_args
            assert call_args is not None
            kwargs = call_args.kwargs
            filter_query = kwargs.get("filter_query", "")

            # Expected: assigned_to = "user\" || true || \""
            sanitized = sanitize_param(malicious_user_id)
            expected_part = f'assigned_to = "{sanitized}"'

            # This assertion will fail before the fix
            assert expected_part in filter_query, f"Filter query '{filter_query}' does not contain sanitized user_id '{expected_part}'"

    @pytest.mark.asyncio
    async def test_analytics_sanitization(self):
        # Mock get_record to return a user so get_user_statistics doesn't fail early
        with patch("src.core.db_client.get_record", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "u1", "name": "User"}

            with patch("src.core.db_client.list_records", new_callable=AsyncMock) as mock_list:
                # We need to return some pending chores so that it proceeds to query logs
                # Chore ID also has injection payload
                malicious_chore_id = 'chore" || true || "'

                async def side_effect(*args, **kwargs):
                    fq = kwargs.get("filter_query", "")
                    if 'current_state = "PENDING_VERIFICATION"' in fq:
                        return [{"id": malicious_chore_id}]
                    return []

                mock_list.side_effect = side_effect

                malicious_user_id = 'user" || true || "'

                try:
                    await analytics_service.get_user_statistics(user_id=malicious_user_id)
                except Exception:
                    # Ignore errors downstream
                    pass

                # Check if filter query for logs was sanitized
                log_query_found = False
                for call in mock_list.call_args_list:
                    fq = call.kwargs.get("filter_query", "")
                    if 'action = "claimed_completion"' in fq:
                        sanitized_user = sanitize_param(malicious_user_id)
                        sanitized_chore = sanitize_param(malicious_chore_id)

                        # Check user_id sanitization
                        if f'user_id = "{sanitized_user}"' in fq:
                             # Check chore_id sanitization in OR clause
                             if f'chore_id = "{sanitized_chore}"' in fq:
                                 log_query_found = True

                assert log_query_found, "Sanitized query for logs not found"
