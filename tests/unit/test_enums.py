"""Tests for enum completeness and string behaviour."""

from __future__ import annotations

import pytest

from choresir.enums import (
    JobStatus,
    MemberRole,
    MemberStatus,
    TaskStatus,
    TaskVisibility,
    VerificationMode,
)

_ENUM_EXPECTED_MEMBERS = [
    (TaskStatus, {"pending", "claimed", "verified"}),
    (VerificationMode, {"none", "peer", "partner"}),
    (MemberRole, {"admin", "member"}),
    (MemberStatus, {"pending", "active"}),
    (JobStatus, {"pending", "processing", "done", "failed"}),
    (TaskVisibility, {"shared", "personal"}),
]

_ALL_ENUMS = [cls for cls, _ in _ENUM_EXPECTED_MEMBERS]


@pytest.mark.parametrize(("enum_cls", "expected"), _ENUM_EXPECTED_MEMBERS)
def test_enum_has_expected_members(enum_cls, expected):
    assert {m.value for m in enum_cls} == expected


@pytest.mark.parametrize("enum_cls", _ALL_ENUMS)
def test_enum_values_are_lowercase(enum_cls):
    for member in enum_cls:
        assert member.value == member.value.lower()


@pytest.mark.parametrize("enum_cls", _ALL_ENUMS)
def test_enum_str_returns_value(enum_cls):
    for member in enum_cls:
        assert str(member) == member.value
