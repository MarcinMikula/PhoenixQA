"""
test_policy_only_provider.py

Sprint 8 (Gap #9). Pure logic against collector_metadata — no live DOM,
no LLM. Ground-truth shapes mirror the two Chaos App modes already
live-verified against the real LLM path in Sprint 6B
(visibilityDelay.jsx PERMANENT/TRANSIENT) — same collector_metadata
shape, so this test suite is directly comparable to that live evidence,
not a different scenario.
"""
import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.ai.policy_only_provider import PolicyOnlyProvider
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind


def _context(actionability_reason=ActionabilityReason.VISIBLE,
             category=FailureCategory.ACTIONABILITY,
             collector_metadata=None):
    return HealingContext(
        broken_selector="[data-testid='password-ab12']",
        error_message="Locator.fill: Timeout 30000ms exceeded.",
        dom_snapshot="<input data-testid=\"password-x7f2\">",
        page_url="http://localhost:5173/",
        original_code="fill",
        category=category,
        actionability_reason=actionability_reason,
        collector_metadata=collector_metadata,
    )


@pytest.mark.unit
class TestPolicyOnlyProviderVisible:
    def test_state_changed_yields_wait_and_retry(self):
        # Mirrors Chaos App's TRANSIENT mode, live-verified against
        # llama3.2 in Sprint 6B — same ground truth, zero-LLM path.
        context = _context(collector_metadata={
            "target_state_changed_during_observation": True,
            "observation_window_ms": 1200,
        })
        result = PolicyOnlyProvider().analyze_failure(context)

        assert isinstance(result.action, ActionabilityStrategy)
        assert result.action.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY
        assert result.action.suggested_wait_ms == 1200
        assert result.action.confidence == 1.0
        # This is a direct decision, not a correction of someone else's
        # proposal — corrected_by_policy fields stay at their defaults.
        assert result.action.corrected_by_policy is False

    def test_state_unchanged_yields_no_safe_recovery(self):
        # Mirrors Chaos App's PERMANENT mode, live-verified against
        # llama3.2 in Sprint 6B — same ground truth, zero-LLM path.
        context = _context(collector_metadata={
            "target_state_changed_during_observation": False,
            "observation_window_ms": 1200,
        })
        result = PolicyOnlyProvider().analyze_failure(context)

        assert result.action.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert result.action.confidence == 1.0

    def test_missing_collector_metadata_defaults_to_no_change(self):
        # Same fail-safe default validate_visible_strategy() uses — no
        # evidence of change means no basis to recommend waiting.
        context = _context(collector_metadata=None)
        result = PolicyOnlyProvider().analyze_failure(context)

        assert result.action.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY

    def test_missing_metadata_key_defaults_to_no_change(self):
        context = _context(collector_metadata={"observation_window_ms": 1200})
        result = PolicyOnlyProvider().analyze_failure(context)

        assert result.action.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY

    def test_raises_not_implemented_for_receives_events(self):
        # Deliberately excluded — see module docstring: RECEIVES_EVENTS'
        # weaker, declaration-based evidence isn't a fair comparison
        # target for a policy-only baseline.
        context = _context(actionability_reason=ActionabilityReason.RECEIVES_EVENTS)
        with pytest.raises(NotImplementedError, match="ACTIONABILITY/VISIBLE only"):
            PolicyOnlyProvider().analyze_failure(context)

    def test_raises_not_implemented_for_locator_resolution(self):
        context = _context(category=FailureCategory.LOCATOR_RESOLUTION, actionability_reason=None)
        with pytest.raises(NotImplementedError, match="ACTIONABILITY/VISIBLE only"):
            PolicyOnlyProvider().analyze_failure(context)

    def test_health_check_always_true_no_network_dependency(self):
        assert PolicyOnlyProvider().health_check() is True
