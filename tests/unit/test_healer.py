"""
test_healer.py

Unit tests for Healer's Safe Mode and Autonomous Mode branches. Uses
mocks for the provider/collector — real page/LLM round-trips are
exercised via manual end-to-end testing against Chaos App, not here.

Safe Mode tests cover the bug caught in a real end-to-end run: a
zero-confidence/empty-selector proposal (from a parse failure) must be
auto-rejected BEFORE asking the human to review it.

Autonomous Mode tests (Sprint 5) cover the three-stage gate: budget
check before calling the LLM, lifecycle timing, and confidence threshold
— plus confirm budget consumption happens even when an attempt fails.
"""
import json

from unittest.mock import MagicMock

import pytest

from phoenix.ai.base_provider import HealingContext, HealingProposal, ProviderResult
from phoenix.collector.failure_classifier import FailureType
from phoenix.healing.autonomous_policy import AutonomousPolicy
from phoenix.healing.healer import (
    Healer,
    HealingFailedError,
    HealingLimitExceededError,
    HealingRejectedError,
)


def _make_context():
    return HealingContext(
        broken_selector="[data-testid='btn-login']",
        error_message="Locator.click: Timeout 10000ms exceeded.",
        dom_snapshot="<form>...</form>",
        page_url="http://localhost:5173/",
        original_code="click",
        failure_type=FailureType.SELECTOR_NOT_FOUND,
    )


def _make_healer(healing_mode="safe", policy=None):
    """
    Bypasses __init__ to avoid constructing a real provider/collector —
    every test wires its own mocks onto the bare instance.
    """
    settings = MagicMock()
    settings.healing_mode = healing_mode
    settings.ai_provider = "ollama"  # must be a real string — log_decision() JSON-serializes it

    healer = Healer.__new__(Healer)
    healer.settings = settings
    healer.collector = MagicMock()
    healer.collector.collect.return_value = _make_context()
    healer.provider = MagicMock()
    healer.policy = policy or AutonomousPolicy()
    from phoenix.healing.autonomous_policy import HealingBudget
    healer.budget = HealingBudget(policy=healer.policy)
    return healer


@pytest.mark.unit
class TestHealerSafeMode:
    def test_empty_proposal_is_auto_rejected_without_prompting_human(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        healer = _make_healer(healing_mode="safe")
        # Simulates response_parser.py's _fallback_proposal() output —
        # exactly what a truncated/malformed LLM response produces.
        healer.provider.analyze_failure.return_value = ProviderResult(
            proposal=HealingProposal(
                proposed_selector="",
                confidence=0.0,
                reasoning="Failed to parse LLM response: JSON parse error",
                alternative_selectors=[],
                raw_response="{truncated...",
            )
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
        healer = _make_healer(healing_mode="safe")
        healer.provider.analyze_failure.return_value = ProviderResult(
            proposal=HealingProposal(
                proposed_selector="[data-testid='btn-login-x1y2']",
                confidence=0.15,
                reasoning="Low confidence guess based on partial match",
                alternative_selectors=[],
                raw_response="{...}",
            )
        )

        result = healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")
        assert result == "[data-testid='btn-login-x1y2']"


@pytest.mark.unit
class TestHealerAutonomousMode:
    def test_high_confidence_proposal_is_accepted_without_human_prompt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        policy = AutonomousPolicy(min_confidence=0.75)
        healer = _make_healer(healing_mode="autonomous", policy=policy)
        healer.provider.analyze_failure.return_value = ProviderResult(
            proposal=HealingProposal(
                proposed_selector="[data-testid='btn-login-4t64']",
                confidence=0.95,
                reasoning="Found matching base name with rotated suffix",
                alternative_selectors=[],
                raw_response="{...}",
            ),
            input_tokens=800,
            output_tokens=120,
        )

        result = healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")
        assert result == "[data-testid='btn-login-4t64']"
        # Budget must reflect the real token usage reported by the provider.
        assert healer.budget.input_tokens_used == 800
        assert healer.budget.output_tokens_used == 120
        assert healer.budget.attempts_total == 1

    def test_log_entry_includes_provider_tokens_and_attempt_number(self, tmp_path, monkeypatch):
        # Verifies the log enrichment is actually wired through, not just
        # "doesn't crash" — provider/elapsed_ms/tokens/attempt were all
        # already available in memory before this fix; the bug was that
        # they were silently discarded instead of reaching the log.
        monkeypatch.chdir(tmp_path)
        policy = AutonomousPolicy(min_confidence=0.75)
        healer = _make_healer(healing_mode="autonomous", policy=policy)
        healer.provider.analyze_failure.return_value = ProviderResult(
            proposal=HealingProposal(
                proposed_selector="[data-testid='btn-login-4t64']",
                confidence=0.95,
                reasoning="Found matching base name with rotated suffix",
                alternative_selectors=[],
                raw_response="{...}",
            ),
            input_tokens=800,
            output_tokens=120,
        )

        healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")

        log_path = tmp_path / "healing_decisions.log"
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["provider"] == "ollama"
        assert entry["input_tokens"] == 800
        assert entry["output_tokens"] == 120
        assert entry["attempt"] == 1
        # elapsed_ms must be a real measured value, not None/missing —
        # exact value is non-deterministic (real timer), just confirm
        # it's a sane non-negative number.
        assert isinstance(entry["elapsed_ms"], int)
        assert entry["elapsed_ms"] >= 0

    def test_confidence_below_policy_threshold_is_rejected_no_human_involved(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # If this test ever accidentally routes to Safe Mode's human
        # prompt, it will hang on input() rather than silently pass —
        # no need to assert that separately.
        policy = AutonomousPolicy(min_confidence=0.90)
        healer = _make_healer(healing_mode="autonomous", policy=policy)
        healer.provider.analyze_failure.return_value = ProviderResult(
            proposal=HealingProposal(
                proposed_selector="[data-testid='btn-login-4t64']",
                confidence=0.60,  # below the 0.90 threshold
                reasoning="Plausible but not certain match",
                alternative_selectors=[],
                raw_response="{...}",
            )
        )

        with pytest.raises(HealingRejectedError, match="below policy threshold"):
            healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")
        # Still counts as a spent attempt even though it was rejected.
        assert healer.budget.attempts_total == 1

    def test_budget_already_exceeded_blocks_attempt_before_calling_provider(self, tmp_path, monkeypatch):
        # Core Gap #10 guarantee: a session out of budget must not spend
        # one more LLM call finding that out.
        monkeypatch.chdir(tmp_path)
        policy = AutonomousPolicy(max_attempts_total=1)
        healer = _make_healer(healing_mode="autonomous", policy=policy)
        healer.budget.record_attempt("[data-testid='username']")  # pre-spend the only attempt

        with pytest.raises(HealingLimitExceededError, match="max_attempts_total"):
            healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")

        # The provider must never have been called — budget was already
        # exhausted before any analysis was attempted.
        healer.provider.analyze_failure.assert_not_called()

    def test_provider_exception_raises_healing_failed_and_still_consumes_budget(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        healer = _make_healer(healing_mode="autonomous")
        healer.provider.analyze_failure.side_effect = RuntimeError("Ollama connection refused")

        with pytest.raises(HealingFailedError, match="Ollama connection refused"):
            healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")

        # A crashed attempt still consumed budget — it was still an
        # attempt, even though nothing usable came back.
        assert healer.budget.attempts_total == 1

    def test_total_attempts_limit_trips_across_different_selectors(self, tmp_path, monkeypatch):
        # The exact scenario from the design discussion: N different
        # selectors healing once each must still trip a total limit,
        # not just a per-selector one.
        monkeypatch.chdir(tmp_path)
        policy = AutonomousPolicy(max_attempts_total=2, min_confidence=0.5)
        healer = _make_healer(healing_mode="autonomous", policy=policy)
        healer.provider.analyze_failure.return_value = ProviderResult(
            proposal=HealingProposal(
                proposed_selector="[data-testid='x']",
                confidence=0.9,
                reasoning="ok",
                alternative_selectors=[],
                raw_response="{...}",
            )
        )

        healer.attempt_heal("[data-testid='username']", Exception("timeout"), "fill")
        healer.attempt_heal("[data-testid='password']", Exception("timeout"), "fill")

        # Third DIFFERENT selector — budget is still exhausted globally.
        with pytest.raises(HealingLimitExceededError):
            healer.attempt_heal("[data-testid='btn-login']", Exception("timeout"), "click")
