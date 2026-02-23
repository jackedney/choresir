"""Test configuration security and validation."""

import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_dev_missing_secrets_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that in dev mode, missing secrets get safe defaults."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("IS_PRODUCTION", raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    # Assert defaults are set
    assert settings.secret_key == "insecure_dev_secret_key"
    assert settings.admin_password == "insecure_dev_admin_password"
    assert not settings.is_production


def test_prod_missing_secrets_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that in prod mode, missing secrets raise error."""
    # Ensure IS_PRODUCTION=true
    monkeypatch.setenv("IS_PRODUCTION", "true")
    # Ensure secrets are missing
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)  # type: ignore[call-arg]

    # Check that error mentions the missing fields
    assert "SECRET_KEY must be set" in str(excinfo.value)
    # The validation stops at first failure? No, pydantic usually collects all.
    # But I raised ValueError inside 'if'.
    # If I raise one error, it stops there.
    # My validator checks secret_key first.


def test_prod_short_secret_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that in prod mode, short secret key raises error."""
    monkeypatch.setenv("IS_PRODUCTION", "true")
    monkeypatch.setenv("ADMIN_PASSWORD", "secure")
    monkeypatch.setenv("SECRET_KEY", "short")

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "at least 12 characters" in str(excinfo.value)


def test_prod_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify valid prod config."""
    monkeypatch.setenv("IS_PRODUCTION", "true")
    monkeypatch.setenv("ADMIN_PASSWORD", "secure")
    monkeypatch.setenv("SECRET_KEY", "long_secure_secret_key_123")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.is_production
    assert settings.secret_key == "long_secure_secret_key_123"
