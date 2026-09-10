"""
test_safe_mode.py

Sprint 8 (Option A, narrowed). request_human_review() (the original,
SelectorReplacement-shaped function) has never had direct unit tests —
its Healer-level effects are covered via monkeypatch in test_healer.py
instead. request_human_review_actionability() has real, standalone
branching logic worth testing directly, though: two distinct auto-reject
paths (NO_SAFE_RECOVERY, unsupported strategy kind) that must never
reach input() — if either regressed to prompting, a test relying on
monkeypatching this function away (as test_healer.py does for the
accept/reject cases) would hide the bug, since it never exercises the
real function body. These tests do.
"""
from unittest.mock import patch

import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind
from phoenix.healing.safe_mode import request_human_review_actionability


def _context():
    return HealingContext(
        broken_selector="[data-testid='password']",
        error_message="Locator.fill: Timeout 30000ms exceeded.",
        dom_snapshot="<input data-testid='password'>",
        page_url="http://localhost:5173/",
        original_code="fill",
        category=FailureCategory.ACTIONABILITY,
        actionability_reason=ActionabilityReason.VISIBLE,
    )


@pytest.mark.unit
class TestRequestHumanReviewActionability:
    def test_no_safe_recovery_auto_rejects_without_calling_input(self):
        action = ActionabilityStrategy(
            confidence=1.0,
            reasoning="state never changed",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
        )
        with patch("builtins.input") as mock_input:
            result = request_human_review_actionability(_context(), action)

        assert result is False
        mock_input.assert_not_called()

    def test_unsupported_strategy_kind_auto_rejects_without_calling_input(self):
        # Defensive path: VISIBLE's own prompt is restricted to
        # WAIT_AND_RETRY/NO_SAFE_RECOVERY, but this function must not
        # assume that restriction always holds upstream — a genuinely
        # unexpected strategy kind reaching here is a scope bug, not a
        # human decision, and must not hang on input().
        action = ActionabilityStrategy(
            confidence=0.9,
            reasoning="unexpected",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.FORCE_NOT_ALLOWED,
        )
        with patch("builtins.input") as mock_input:
            result = request_human_review_actionability(_context(), action)

        assert result is False
        mock_input.assert_not_called()

    def test_wait_and_retry_prompts_and_returns_true_on_yes(self):
        action = ActionabilityStrategy(
            confidence=0.9,
            reasoning="state changed during observation",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
            suggested_wait_ms=1200,
        )
        with patch("builtins.input", return_value="y"):
            result = request_human_review_actionability(_context(), action)

        assert result is True

    def test_wait_and_retry_prompts_and_returns_false_on_no(self):
        action = ActionabilityStrategy(
            confidence=0.9,
            reasoning="state changed during observation",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
            suggested_wait_ms=1200,
        )
        with patch("builtins.input", return_value="n"):
            result = request_human_review_actionability(_context(), action)

        assert result is False

    def test_wait_and_retry_reprompts_on_invalid_answer(self):
        action = ActionabilityStrategy(
            confidence=0.9,
            reasoning="state changed",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
            suggested_wait_ms=1200,
        )
        with patch("builtins.input", side_effect=["maybe", "y"]) as mock_input:
            result = request_human_review_actionability(_context(), action)

        assert result is True
        assert mock_input.call_count == 2