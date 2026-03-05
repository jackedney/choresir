"""Tests for task state machine transitions."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from choresir.enums import TaskStatus
from choresir.errors import InvalidTransitionError
from choresir.services.task_service import _VALID_TRANSITIONS, transition_task
from tests.conftest import make_task


class TestValidTransitions:
    def test_pending_to_claimed(self):
        task = make_task(status=TaskStatus.PENDING)
        transition_task(task, TaskStatus.CLAIMED)
        assert task.status == TaskStatus.CLAIMED

    def test_claimed_to_verified(self):
        task = make_task(status=TaskStatus.CLAIMED)
        transition_task(task, TaskStatus.VERIFIED)
        assert task.status == TaskStatus.VERIFIED

    def test_claimed_to_pending(self):
        task = make_task(status=TaskStatus.CLAIMED)
        transition_task(task, TaskStatus.PENDING)
        assert task.status == TaskStatus.PENDING


class TestInvalidTransitions:
    def test_pending_to_verified_raises(self):
        task = make_task(status=TaskStatus.PENDING)
        with pytest.raises(InvalidTransitionError):
            transition_task(task, TaskStatus.VERIFIED)

    def test_verified_to_any_raises(self):
        for target in TaskStatus:
            task = make_task(status=TaskStatus.VERIFIED)
            with pytest.raises(InvalidTransitionError):
                transition_task(task, target)

    def test_pending_to_pending_raises(self):
        task = make_task(status=TaskStatus.PENDING)
        with pytest.raises(InvalidTransitionError):
            transition_task(task, TaskStatus.PENDING)

    def test_error_carries_context(self):
        task = make_task(status=TaskStatus.PENDING)
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_task(task, TaskStatus.VERIFIED)
        assert exc_info.value.current == TaskStatus.PENDING
        assert exc_info.value.target == TaskStatus.VERIFIED


class TestTransitionsHypothesis:
    @given(
        current=st.sampled_from(TaskStatus),
        target=st.sampled_from(TaskStatus),
    )
    def test_invalid_transitions_raise(self, current, target):
        if target not in _VALID_TRANSITIONS.get(current, frozenset()):
            task = make_task(status=current)
            with pytest.raises(InvalidTransitionError):
                transition_task(task, target)
