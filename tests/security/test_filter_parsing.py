"""Test security vulnerabilities in filter parsing."""

import pytest

from src.core import db_client


@pytest.mark.unit
def test_filter_parsing_escaped_double_quotes():
    """Test that filter parser correctly handles escaped double quotes."""
    # This value simulates what sanitize_param produces for 'foo"bar'
    # json.dumps('foo"bar') -> '"foo\\"bar"' -> inner is 'foo\\"bar'
    val = 'foo\\"bar'
    query = f'name = "{val}"'

    _, param = db_client._parse_single_comparison(query)

    # We expect the parameter to be the original value 'foo"bar'
    # Currently it fails and returns 'foo\\' (escaped and truncated)
    assert param == 'foo"bar', f"Expected 'foo\"bar', got '{param}'"


@pytest.mark.unit
def test_filter_parsing_multiple_escaped_quotes():
    """Test that filter parser correctly handles multiple escaped quotes."""
    val = 'a\\"b\\"c'
    query = f'name = "{val}"'

    _, param = db_client._parse_single_comparison(query)

    assert param == 'a"b"c', f"Expected 'a\"b\"c', got '{param}'"


@pytest.mark.unit
def test_filter_parsing_single_quotes_escaped():
    """Test that filter parser correctly handles escaped single quotes in single-quoted strings."""
    # User manually constructing: name = 'O\'Reilly'
    # escape for python string: 'O\\\'Reilly'
    query = "name = 'O\\'Reilly'"

    _, param = db_client._parse_single_comparison(query)

    assert param == "O'Reilly", f"Expected \"O'Reilly\", got '{param}'"


@pytest.mark.unit
def test_filter_parsing_backslash():
    """Test that filter parser correctly handles backslashes."""
    # Logic: val = '\' -> sanitize_param -> '\\'
    # Constructed query becomes: name = "\\"
    query = 'name = "\\\\"'

    _, param = db_client._parse_single_comparison(query)

    assert param == "\\", f"Expected '\\', got '{param}'"


@pytest.mark.unit
def test_sanitize_param_integration():
    """Test full integration with sanitize_param."""
    original_value = 'foo"bar'
    sanitized = db_client.sanitize_param(original_value)
    query = f'name = "{sanitized}"'

    _, param = db_client._parse_single_comparison(query)

    assert param == original_value


@pytest.mark.unit
def test_injection_attempt_is_parameterized():
    """Test that injection attempts are treated as values, not SQL."""
    # Attempt to close quote and add OR 1=1
    # value being tested: foo" OR 1=1 --
    # sanitize_param converts to: foo\" OR 1=1 --
    # query becomes name = "foo\" OR 1=1 --"

    malicious_value = 'foo" OR 1=1 --'
    sanitized = db_client.sanitize_param(malicious_value)
    query = f'name = "{sanitized}"'

    cond, param = db_client._parse_single_comparison(query)

    assert cond == "name = ?"
    assert param == malicious_value
