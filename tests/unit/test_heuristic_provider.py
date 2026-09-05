"""
test_heuristic_provider.py

Sprint 8 (Gap #9). Pure logic, no live DOM/LLM needed — HeuristicProvider
only ever reads HealingContext.dom_snapshot as a plain string, same as
any other provider's analyze_failure() receives it.
"""
import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.ai.heuristic_provider import HeuristicProvider
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.actions import SelectorReplacement


def _context(broken_selector, dom_snapshot, category=FailureCategory.LOCATOR_RESOLUTION,
             actionability_reason=None):
    return HealingContext(
        broken_selector=broken_selector,
        error_message="Locator.fill: Timeout 30000ms exceeded.",
        dom_snapshot=dom_snapshot,
        page_url="http://localhost:5173/",
        original_code="fill",
        category=category,
        actionability_reason=actionability_reason,
    )


@pytest.mark.unit
class TestHeuristicProviderLocatorResolution:
    def test_matches_rotated_data_testid_correctly(self):
        context = _context(
            "[data-testid='username-ab12']",
            "<input data-testid=\"username-x7f2\" id=\"chaos-username\">",
        )
        result = HeuristicProvider().analyze_failure(context)

        assert isinstance(result.action, SelectorReplacement)
        assert result.action.proposed_selector == "[data-testid='username-x7f2']"
        assert result.action.confidence > 0.5

    def test_prefers_higher_weighted_attribute_on_a_genuine_tie(self):
        # Both values strip down to the exact same base name ("email"),
        # so similarity is identical (1.0) for both — only the weight
        # tie-breaker can decide. data-testid (5) must win over
        # placeholder (3).
        context = _context(
            "[data-testid='email-ab12']",
            "<input placeholder=\"email-1234\" data-testid=\"email-9k2q\">",
        )
        result = HeuristicProvider().analyze_failure(context)

        assert result.action.proposed_selector == "[data-testid='email-9k2q']"
        # Confidence reflects match SIMILARITY, not the tie-break nudge —
        # a perfect match is reported as 1.0, regardless of which
        # attribute source it came from.
        assert result.action.confidence == 1.0

    def test_id_attribute_rendered_with_hash_prefix(self):
        context = _context(
            "[data-testid='username-ab12']",
            "<input id=\"username-x7f2\">",
        )
        result = HeuristicProvider().analyze_failure(context)

        assert result.action.proposed_selector == "#username-x7f2"

    def test_perfect_match_on_lowest_weighted_attribute_still_passes_threshold(self):
        # Regression guard: an earlier version multiplied similarity by
        # normalized weight, which meant id (weight 2/5=0.4) could never
        # mathematically clear a 0.5 threshold even with a PERFECT
        # textual match — a low-weight attribute source silently
        # disqualified good matches instead of just losing ties. id is
        # the lowest-weighted source this provider considers; a perfect
        # match there must still win.
        context = _context(
            "[data-testid='username-ab12']",
            "<input id=\"username\">",
        )
        result = HeuristicProvider().analyze_failure(context)

        assert result.action.proposed_selector == "#username"
        assert result.action.confidence == 1.0

    def test_no_candidate_above_threshold_returns_empty_zero_confidence(self):
        context = _context(
            "[data-testid='username-ab12']",
            "<button data-testid=\"btn-submit-x1y2\">Submit</button>",
        )
        result = HeuristicProvider().analyze_failure(context)

        assert result.action.proposed_selector == ""
        assert result.action.confidence == 0.0

    def test_empty_dom_snapshot_returns_empty_zero_confidence_not_a_crash(self):
        context = _context(
            "[data-testid='username-ab12']",
            "<!-- no matching elements found in light DOM or shadow roots -->",
        )
        result = HeuristicProvider().analyze_failure(context)

        assert result.action.proposed_selector == ""
        assert result.action.confidence == 0.0

    def test_raises_not_implemented_for_actionability_category(self):
        # Matches the original Gap #9 scope exactly — this baseline is
        # LOCATOR_RESOLUTION only. ACTIONABILITY gets its own separate
        # baseline (PolicyOnlyProvider), not this class extended.
        context = _context(
            "[data-testid='password']",
            "<input data-testid=\"password-x7f2\">",
            category=FailureCategory.ACTIONABILITY,
            actionability_reason=ActionabilityReason.VISIBLE,
        )
        with pytest.raises(NotImplementedError, match="LOCATOR_RESOLUTION only"):
            HeuristicProvider().analyze_failure(context)

    def test_health_check_always_true_no_network_dependency(self):
        assert HeuristicProvider().health_check() is True

    def test_accepts_no_settings_argument(self):
        # Interface parity with real providers (both take Settings), but
        # nothing here actually reads it yet — must not require one.
        provider = HeuristicProvider()
        assert provider.settings is None
