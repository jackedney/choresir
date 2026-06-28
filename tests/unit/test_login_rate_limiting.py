from unittest import mock

import pytest

from choresir.admin.pages import (
    _check_rate_limit,
    _login_attempts,
    _login_attempts_lock,
)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    with _login_attempts_lock:
        _login_attempts.clear()
    yield
    with _login_attempts_lock:
        _login_attempts.clear()


def test_rate_limit_enforcement():
    ip = "1.1.1.1"
    for _ in range(5):
        assert _check_rate_limit(ip) is True

    assert _check_rate_limit(ip) is False


def test_rate_limit_expiry():
    ip = "2.2.2.2"
    with mock.patch("time.monotonic", return_value=1000.0):
        for _ in range(5):
            assert _check_rate_limit(ip) is True
        assert _check_rate_limit(ip) is False

    with mock.patch("time.monotonic", return_value=1061.0):
        assert _check_rate_limit(ip) is True


def test_size_bounding():
    # Fill up the rate limiter
    for i in range(1001):
        _check_rate_limit(f"10.0.0.{i}")

    with _login_attempts_lock:
        assert len(_login_attempts) <= 1000
