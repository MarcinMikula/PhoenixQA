"""
test_decision_logger.py

Unit tests for log_decision. Pure file I/O — no live Playwright page or
Ollama call needed, unlike the rest of Sprint 4 (Healer/safe_mode require
a real browser page and a real LLM round-trip, so they're exercised via
manual integration testing against Chaos App, not here).

Sprint 6B: failure_type assertions replaced with failure_category /
actionability_reason / failure_label, matching HealingContext's new
fields (see LEARNINGS.md "Sprint 6B (decision)").
"""
import json

import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind, SelectorReplacement
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.decision_logger import log_decision


def _sample_context():
    return HealingContext(
        broken_selector="[data-testid='username-ab12']",
        error_message="Timeout 10000ms exceeded waiting for locator",
        dom_snapshot="<form>...</form>",
        page_url="http://localhost:5173/",
        original_code="fill",
        category=FailureCategory.LOCATOR_RESOLUTION,
    )


def _sample_actionability_context():
    return HealingContext(
        broken_selector="#target",
        error_message="Locator.click: Timeout 300ms exceeded.",
        dom_snapshot="<button id='target'>Click me</button>",
        page_url="http://localhost:5173/",
        original_code="click",
        category=FailureCategory.ACTIONABILITY,
        actionability_reason=ActionabilityReason.STABLE,
    )


def _sample_proposal():
    return SelectorReplacement(
        proposed_selector="[data-testid='username-x7f2']",
        confidence=0.92,
        reasoning="Same form position, matching data-testid prefix",
        alternative_selectors=["#chaos-username"],
        raw_response='{"proposed_selector": "..."}',
    )


@pytest.mark.unit
class TestLogDecision:
    def test_writes_one_json_line_with_expected_fields(self, tmp_path):
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=True, log_path=str(log_path))

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["broken_selector"] == "[data-testid='username-ab12']"
        assert entry["proposed_selector"] == "[data-testid='username-x7f2']"
        assert entry["confidence"] == 0.92
        assert entry["accepted"] is True
        assert entry["failure_category"] == "locator_resolution"
        assert entry["actionability_reason"] is None
        assert entry["failure_label"] == "locator_resolution"
        assert entry["mode"] == "safe"
        assert "timestamp" in entry

    def test_actionability_context_produces_combined_failure_label(self, tmp_path):
        # Confirms the "category:reason" format described in
        # LEARNINGS.md "Sprint 6B (decision)" actually gets written,
        # not just designed.
        log_path = tmp_path / "healing_decisions.log"
        log_decision(
            _sample_actionability_context(), _sample_proposal(), accepted=True, log_path=str(log_path)
        )

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["failure_category"] == "actionability"
        assert entry["actionability_reason"] == "stable"
        assert entry["failure_label"] == "actionability:stable"

    def test_includes_raw_response_for_post_hoc_diagnosis(self, tmp_path):
        # Caught via a real end-to-end run: a parse-failure entry with no
        # raw_response gives no way to see WHAT the model actually
        # returned — "JSON parse error" alone isn't enough to diagnose
        # or fix a prompt. This field is the difference between a log
        # you can debug from and one you can only shrug at.
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=True, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["raw_response"] == '{"proposed_selector": "..."}'

    def test_appends_rather_than_overwrites(self, tmp_path):
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=True, log_path=str(log_path))
        log_decision(_sample_context(), _sample_proposal(), accepted=False, log_path=str(log_path))

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["accepted"] is True
        assert second["accepted"] is False

    def test_rejected_decision_is_logged_too_not_just_accepted(self, tmp_path):
        # The log needs the full picture for post-hoc review (per direct
        # discussion) — rejections are just as important to trace as
        # acceptances, not a silent path.
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=False, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["accepted"] is False
        assert entry["reasoning"] == "Same form position, matching data-testid prefix"

    def test_mode_is_explicit_not_hardcoded(self, tmp_path):
        # Caught via a real live run: log_decision() previously hardcoded
        # "mode": "safe" unconditionally, so every Autonomous Mode
        # decision was silently mislabeled in the log — harmless-looking
        # but would have corrupted any future Safe-vs-Autonomous analysis
        # built on this field. This test protects the fix: mode must
        # reflect what the caller actually passes, defaulting to "safe"
        # only when genuinely not specified.
        log_path = tmp_path / "healing_decisions.log"
        log_decision(
            _sample_context(), _sample_proposal(), accepted=True,
            mode="autonomous", log_path=str(log_path),
        )

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["mode"] == "autonomous"

    def test_mode_defaults_to_safe_when_not_specified(self, tmp_path):
        # Backward-compatible default — existing call sites that don't
        # pass mode explicitly still log "safe", matching prior behavior
        # for genuinely Safe Mode callers.
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=True, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["mode"] == "safe"


@pytest.mark.unit
class TestLogDecisionActionabilityStrategy:
    """
    Sprint 8 (Option A, narrowed). Before this, log_decision() would
    have raised AttributeError on action.proposed_selector for an
    ActionabilityStrategy — Healer never called it with one, since it
    rejected before reaching this function. Now that VISIBLE execution
    calls it directly, log_decision() must handle both HealingAction
    shapes in one schema without crashing on either.
    """

    def test_actionability_strategy_does_not_crash_and_has_null_selector_fields(self, tmp_path):
        log_path = tmp_path / "healing_decisions.log"
        action = ActionabilityStrategy(
            confidence=0.95,
            reasoning="state changed during observation",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
            suggested_wait_ms=1200,
        )
        # The real assertion here is simply that this does not raise.
        log_decision(_sample_actionability_context(), action, accepted=True, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["proposed_selector"] is None
        assert entry["alternative_selectors"] is None

    def test_actionability_strategy_fields_are_captured(self, tmp_path):
        log_path = tmp_path / "healing_decisions.log"
        action = ActionabilityStrategy(
            confidence=0.95,
            reasoning="state changed during observation",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
            suggested_wait_ms=1200,
        )
        log_decision(_sample_actionability_context(), action, accepted=True, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["strategy"] == "wait_and_retry"
        assert entry["suggested_wait_ms"] == 1200

    def test_policy_correction_fields_are_captured_when_set(self, tmp_path):
        # actionability_policy.py's correction — a human or dashboard
        # reader needs to see "the model said X, policy corrected to Y,
        # because Z" from the log itself, not just from a live terminal
        # session that already scrolled away.
        log_path = tmp_path / "healing_decisions.log"
        action = ActionabilityStrategy(
            confidence=0.8,
            reasoning="animation-name declared on the target",
            reason=ActionabilityReason.RECEIVES_EVENTS,
            strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
            corrected_by_policy=True,
            original_strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
            policy_reason="no animation/transition evidence in collector_metadata",
        )
        log_decision(_sample_actionability_context(), action, accepted=False, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["corrected_by_policy"] is True
        assert entry["original_strategy"] == "wait_and_retry"
        assert entry["strategy"] == "no_safe_recovery"
        assert "no animation" in entry["policy_reason"]

    def test_uncorrected_actionability_strategy_has_null_correction_fields(self, tmp_path):
        # Default case (no policy intervention needed) must not
        # fabricate correction data — None, not "false"-shaped noise.
        log_path = tmp_path / "healing_decisions.log"
        action = ActionabilityStrategy(
            confidence=1.0,
            reasoning="state never changed",
            reason=ActionabilityReason.VISIBLE,
            strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
        )
        log_decision(_sample_actionability_context(), action, accepted=False, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["corrected_by_policy"] is False
        assert entry["original_strategy"] is None
        assert entry["policy_reason"] is None

    def test_selector_replacement_still_has_null_actionability_fields(self, tmp_path):
        # Symmetric regression guard: a SelectorReplacement entry must
        # not fabricate actionability-shaped data either.
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=True, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["strategy"] is None
        assert entry["suggested_wait_ms"] is None
        assert entry["corrected_by_policy"] is None