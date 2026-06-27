"""
test_healer.py

Unit test for the specific bug caught in a real end-to-end run: a
zero-confidence/empty-selector proposal (from a parse failure) must be
auto-rejected BEFORE asking the human to review it. Answering "y" out of
habit to a meaningless prompt previously led straight into
Locator(""), a CSS parse error unrelated to the original failure.

Uses mocks for the provider/collector — Healer's other paths (real page,
real LLM round-trip) are exercised via manual end-to-end testing against
Chaos App, not here. This test isolates just the auto-reject branch.
"""
from unittest.mock import MagicMock

import pytest

from phoenix.ai.base_provider import HealingContext, HealingProposal
from phoenix.collector.failure_classifier import FailureType
from phoenix.healing.healer import Healer, HealingRejectedError


def _make_context():
    return HealingContext(
        broken_selector="[data-testid='btn-login']",
        error_message="Locator.click: Timeout 10000ms exceeded.",
        dom_snapshot="<form>...</form>",
        page_url="http://localhost:5173/",
        original_code="click",
        failure_type=FailureType.SELECTOR_NOT_FOUND,
    )


@pytest.mark.unit
class TestHealerAutoReject:
    def test_empty_proposal_is_auto_rejected_without_prompting_human(self, tmp_path, monkeypatch):
        # Force the decision log to a throwaway path so this test doesn't
        # write into the real healing_decisions.log.
        monkeypatch.chdir(tmp_path)

        settings = MagicMock()
        settings.healing_mode = "safe"

        healer = Healer.__new__(Healer)  # bypass __init__ — avoid constructing a real provider/collector
        healer.settings = settings
        healer.collector = MagicMock()
        healer.collector.collect.return_value = _make_context()
        healer.provider = MagicMock()
        # Simulates response_parser.py's _fallback_proposal() output —
        # exactly what a truncated/malformed LLM response produces.
        healer.provider.analyze_failure.return_value = HealingProposal(
            proposed_selector="",
            confidence=0.0,
            reasoning="Failed to parse LLM response: JSON parse error",
            alternative_selectors=[],
            raw_response="{truncated...",
        )

        with pytest.raises(HealingRejectedError, match="Auto-rejected without prompting"):
            healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")

        # The human review prompt must never have been reached — if it
        # had, this test would hang waiting for input() in a test run.
        # Reaching this assertion at all is the proof it didn't.

    def test_low_but_nonzero_confidence_still_goes_to_human_review(self, tmp_path, monkeypatch):
        # Guard against an overly broad fix: a genuinely low-confidence
        # but non-empty proposal (the model being honestly unsure, not a
        # parse failure) should still reach the human — only the
        # zero-confidence/empty-selector combination auto-rejects.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "phoenix.healing.healer.request_human_review",
            lambda context, proposal: True,
        )

        settings = MagicMock()
        settings.healing_mode = "safe"

        healer = Healer.__new__(Healer)
        healer.settings = settings
        healer.collector = MagicMock()
        healer.collector.collect.return_value = _make_context()
        healer.provider = MagicMock()
        healer.provider.analyze_failure.return_value = HealingProposal(
            proposed_selector="[data-testid='btn-login-x1y2']",
            confidence=0.15,
            reasoning="Low confidence guess based on partial match",
            alternative_selectors=[],
            raw_response="{...}",
        )

        result = healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")
        assert result == "[data-testid='btn-login-x1y2']"
