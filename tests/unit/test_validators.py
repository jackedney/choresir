"""Unit tests for domain model validators."""

import pytest
from pydantic import ValidationError

from src.domain.user import User


class TestUserNameValidator:
    """Tests for the User.name field validator."""

    def test_name_validator_accepts_unicode(self):
        """Test international names are accepted."""
        valid_names = [
            "김철수",  # Korean
            "José García",  # Spanish
            "Владимир",  # Russian
            "O'Brien",  # Irish
            "Mary-Jane",  # Hyphenated
            "João da Silva",  # Portuguese
            "François",  # French
            "Müller",  # German
            "Søren",  # Danish
        ]
        for name in valid_names:
            user = User(
                id="test-id",
                phone="+1234567890",
                name=name,
            )
            assert user.name == name

    def test_name_validator_rejects_empty(self):
        """Test empty names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            User(id="test-id", phone="+1234567890", name="")

        assert "Name cannot be empty" in str(exc_info.value)

    def test_name_validator_rejects_whitespace_only(self):
        """Test whitespace-only names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            User(id="test-id", phone="+1234567890", name="   ")

        assert "Name cannot be empty" in str(exc_info.value)

    def test_name_validator_rejects_too_long(self):
        """Test names over 50 chars are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            User(id="test-id", phone="+1234567890", name="a" * 51)

        assert "too long" in str(exc_info.value)

    def test_name_validator_accepts_exactly_50_chars(self):
        """Test names exactly 50 chars are accepted."""
        name = "a" * 50
        user = User(id="test-id", phone="+1234567890", name=name)
        assert user.name == name

    def test_name_validator_rejects_emojis(self):
        """Test emojis are rejected."""
        invalid_names = ["🎉emoji", "test🔥name", "party🎊time"]
        for name in invalid_names:
            with pytest.raises(ValidationError) as exc_info:
                User(id="test-id", phone="+1234567890", name=name)

            assert "can only contain" in str(exc_info.value)

    def test_name_validator_rejects_special_chars(self):
        """Test special characters are rejected."""
        invalid_names = [
            "user@123",
            "test#name",
            "name$value",
            "test%user",
            "user&name",
            "test*name",
            "name(test)",
            "test+name",
            "name=value",
            "test[name]",
            "name{test}",
            "test|name",
            "name\\test",
            "test/name",
            "name<test>",
            "test?name",
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError) as exc_info:
                User(id="test-id", phone="+1234567890", name=name)

            assert "can only contain" in str(exc_info.value)

    def test_name_validator_strips_whitespace(self):
        """Test leading/trailing whitespace is stripped."""
        user = User(id="test-id", phone="+1234567890", name="  John Doe  ")
        assert user.name == "John Doe"

    def test_name_validator_accepts_numbers(self):
        """Test names with numbers are accepted (\\w includes digits)."""
        # Note: The \\w pattern with re.UNICODE includes Unicode letters AND digits
        valid_names = ["John2", "User123", "김철수1"]
        for name in valid_names:
            user = User(id="test-id", phone="+1234567890", name=name)
            assert user.name == name

    def test_name_validator_accepts_spaces(self):
        """Test names with multiple spaces are accepted."""
        user = User(id="test-id", phone="+1234567890", name="John Michael Doe")
        assert user.name == "John Michael Doe"

    def test_name_validator_accepts_hyphens(self):
        """Test names with hyphens are accepted."""
        valid_names = ["Mary-Jane", "Jean-Pierre", "Anne-Marie"]
        for name in valid_names:
            user = User(id="test-id", phone="+1234567890", name=name)
            assert user.name == name

    def test_name_validator_accepts_apostrophes(self):
        """Test names with apostrophes are accepted."""
        valid_names = ["O'Brien", "D'Angelo", "L'Amour"]
        for name in valid_names:
            user = User(id="test-id", phone="+1234567890", name=name)
            assert user.name == name
