"""
test_compare_baselines.py

scripts/compare_baselines.py is a standalone comparison tool, not part
of the phoenix package, and its main() genuinely requires a live
browser + live Chaos App + live Ollama — none of that is unit-testable,
by design, same as Healer/safe_mode's live-only pieces.

This file covers only the PURE logic that doesn't need any of that:
the live-correctness check's decision logic (mocked Page), the action
serialization helper, and the ground-truth mapping. Written because
this script could not be run live during development (no browser/Chaos
App/Ollama available in that environment) — these tests are the actual
verification that exists for its logic, not a substitute for the real
comparison run.
"""
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from phoenix.healing.actions import ActionabilityStrategyKind
from scripts.compare_baselines import (
    _BASELINE_PROVIDER_NAME,
    _EXPECTED_STRATEGY,
    _action_to_dict,
    _check_selector_resolves_live,
)


@pytest.mark.unit
class TestCheckSelectorResolvesLive:
    def test_empty_selector_is_never_correct_and_never_queries_the_page(self):
        page = MagicMock()
        assert _check_selector_resolves_live(page, "") is False
        page.locator.assert_not_called()

    def test_selector_resolving_to_exactly_one_element_is_correct(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 1
        assert _check_selector_resolves_live(page, "[data-testid='username-x7f2']") is True

    def test_selector_resolving_to_zero_elements_is_not_correct(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 0
        assert _check_selector_resolves_live(page, "[data-testid='does-not-exist']") is False

    def test_selector_resolving_to_multiple_elements_is_not_correct(self):
        # Same "did this actually re-target the ONE right element"
        # question the collector's own scoring cares about — matching
        # 3 identical rows isn't a correct heal, it's an ambiguous one.
        page = MagicMock()
        page.locator.return_value.count.return_value = 3
        assert _check_selector_resolves_live(page, "[data-testid='ticket-row']") is False

    def test_malformed_selector_raising_is_treated_as_not_correct_not_a_crash(self):
        page = MagicMock()
        page.locator.side_effect = Exception("SyntaxError: invalid selector")
        assert _check_selector_resolves_live(page, "not[[valid") is False


@pytest.mark.unit
class TestActionToDict:
    def test_dataclass_action_is_serialized_via_asdict(self):
        @dataclass
        class FakeAction:
            confidence: float
            proposed_selector: str

        result = _action_to_dict(FakeAction(confidence=0.9, proposed_selector="#x"))
        assert result == {"confidence": 0.9, "proposed_selector": "#x"}

    def test_non_dataclass_action_falls_back_to_repr(self):
        result = _action_to_dict("not a dataclass")
        assert result == {"repr": repr("not a dataclass")}


@pytest.mark.unit
class TestExpectedStrategyGroundTruth:
    def test_permanent_scenario_expects_no_safe_recovery(self):
        # Mirrors Chaos App's visibilityDelay.jsx PERMANENT mode,
        # live-verified against llama3.2 in Sprint 6B.
        assert _EXPECTED_STRATEGY["visible_permanent"] == ActionabilityStrategyKind.NO_SAFE_RECOVERY

    def test_transient_scenario_expects_wait_and_retry(self):
        # Mirrors Chaos App's visibilityDelay.jsx TRANSIENT mode,
        # live-verified against llama3.2 in Sprint 6B.
        assert _EXPECTED_STRATEGY["visible_transient"] == ActionabilityStrategyKind.WAIT_AND_RETRY

    def test_locator_resolution_has_no_fixed_ground_truth(self):
        # By design — see module docstring: correctness there is
        # checked live against the page, not against a fixed value
        # (the rotated suffix changes every mount).
        assert "locator_resolution" not in _EXPECTED_STRATEGY


@pytest.mark.unit
class TestBaselineProviderNameMapping:
    def test_locator_resolution_maps_to_heuristic_provider(self):
        assert _BASELINE_PROVIDER_NAME["locator_resolution"] == "HeuristicProvider"

    def test_both_visible_scenarios_map_to_policy_only_provider(self):
        # Regression guard: an earlier version derived this field from
        # type(action).__module__, which is the SAME module
        # ("phoenix.healing.actions") for both baseline providers -
        # the logged value was silently identical across every
        # scenario. This dict is the fix; this test protects it.
        assert _BASELINE_PROVIDER_NAME["visible_permanent"] == "PolicyOnlyProvider"
        assert _BASELINE_PROVIDER_NAME["visible_transient"] == "PolicyOnlyProvider"

    def test_no_two_scenarios_silently_share_the_wrong_provider(self):
        assert (
            _BASELINE_PROVIDER_NAME["locator_resolution"]
            != _BASELINE_PROVIDER_NAME["visible_permanent"]
        )
