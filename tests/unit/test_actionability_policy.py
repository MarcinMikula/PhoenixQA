"""
test_actionability_policy.py

Unit tests for validate_receives_events_strategy(). Pure logic, no
Playwright/Ollama needed — validates HealingContext.collector_metadata
dicts directly.
"""
import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.actionability_policy import validate_receives_events_strategy
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind


def _context(collector_metadata=None):
    return HealingContext(
        broken_selector="[data-testid='btn-login']",
        error_message="Locator.click: intercepts pointer events",
        dom_snapshot="",
        page_url="http://localhost:5173/",
        original_code="click",
        category=FailureCategory.ACTIONABILITY,
        actionability_reason=ActionabilityReason.RECEIVES_EVENTS,
        collector_metadata=collector_metadata or {},
    )


def _wait_and_retry_strategy(confidence=0.80):
    return ActionabilityStrategy(
        confidence=confidence,
        reasoning="The blocker is persistent but has no dismiss affordance.",
        raw_response="{...}",
        reason=ActionabilityReason.RECEIVES_EVENTS,
        strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
        suggested_wait_ms=300,
    )


@pytest.mark.unit
class TestWaitAndRetryWithoutEvidence:
    def test_corrected_to_no_safe_recovery_when_no_computed_style_at_all(self):
        # The exact real-world case that motivated this module: no
        # blocking_element_computed_style captured (e.g. the DOM probe
        # found nothing), yet the model still proposed wait_and_retry.
        context = _context(collector_metadata={})
        result = validate_receives_events_strategy(_wait_and_retry_strategy(), context)

        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert result.corrected_by_policy is True
        assert result.original_strategy == ActionabilityStrategyKind.WAIT_AND_RETRY
        assert "positive evidence" in result.policy_reason

    def test_corrected_when_computed_style_shows_no_animation_or_transition(self):
        # The real captured pointerEventsOverlay.jsx case: static,
        # persistent styling with animationName "none" (its real CSS
        # default) and transitionProperty "all" (ITS real CSS default —
        # NOT "none", see the regression test below for why this
        # distinction matters).
        context = _context(collector_metadata={
            "blocking_element_computed_style": {
                "position": "fixed", "zIndex": "9999", "pointerEvents": "auto",
                "opacity": "1", "display": "block", "visibility": "visible",
                "animationName": "none", "transitionProperty": "all",
            }
        })
        result = validate_receives_events_strategy(_wait_and_retry_strategy(), context)

        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert result.corrected_by_policy is True

    def test_regression_default_transition_property_is_all_not_none(self):
        # Caught via a real live run (see LEARNINGS.md "Sprint 6B — live
        # re-verification catches a real bug in the policy itself"): the
        # first implementation checked transitionProperty against "none",
        # but transition-property's CSS-spec initial value is "all" —
        # every plain element in a real browser reports "all", not
        # "none". That bug made this exact case (no real evidence,
        # default browser value) silently pass through uncorrected on
        # live Chaos App traffic, even though every mocked unit test at
        # the time happened to use "none" for both fields and could not
        # catch it. This test exists specifically so that mistake cannot
        # silently return.
        context = _context(collector_metadata={
            "blocking_element_computed_style": {
                "animationName": "none", "transitionProperty": "all",
            }
        })
        result = validate_receives_events_strategy(_wait_and_retry_strategy(), context)

        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert result.corrected_by_policy is True

    def test_original_confidence_and_reasoning_are_preserved_on_the_corrected_object(self):
        # The correction changes the strategy, not the model's own
        # stated confidence/reasoning — those stay as evidence of what
        # was actually proposed, alongside the correction metadata.
        context = _context(collector_metadata={})
        original = _wait_and_retry_strategy(confidence=0.83)
        result = validate_receives_events_strategy(original, context)

        assert result.confidence == 0.83
        assert result.reasoning == original.reasoning


@pytest.mark.unit
class TestWaitAndRetryWithEvidence:
    def test_passes_through_when_animation_name_present(self):
        context = _context(collector_metadata={
            "blocking_element_computed_style": {
                "position": "fixed", "animationName": "fade-out", "transitionProperty": "none",
            }
        })
        result = validate_receives_events_strategy(_wait_and_retry_strategy(), context)

        assert result.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY
        assert result.corrected_by_policy is False

    def test_passes_through_when_transition_property_present(self):
        context = _context(collector_metadata={
            "blocking_element_computed_style": {
                "position": "fixed", "animationName": "none", "transitionProperty": "opacity",
            }
        })
        result = validate_receives_events_strategy(_wait_and_retry_strategy(), context)

        assert result.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY
        assert result.corrected_by_policy is False

    def test_original_object_is_not_mutated(self):
        # validate_receives_events_strategy returns a NEW object
        # (dataclasses.replace) — a caller holding a reference to the
        # original (e.g. for the raw DEBUG log) must see it unchanged.
        context = _context(collector_metadata={})
        original = _wait_and_retry_strategy()

        result = validate_receives_events_strategy(original, context)

        assert original.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY
        assert original.corrected_by_policy is False
        assert result is not original


@pytest.mark.unit
class TestNonWaitAndRetryStrategiesPassThroughUnmodified:
    @pytest.mark.parametrize("kind", [
        ActionabilityStrategyKind.DISMISS_BLOCKER,
        ActionabilityStrategyKind.NO_SAFE_RECOVERY,
        ActionabilityStrategyKind.SCROLL_INTO_VIEW,
        ActionabilityStrategyKind.FORCE_NOT_ALLOWED,
    ])
    def test_policy_only_has_one_rule_for_wait_and_retry(self, kind):
        # This policy deliberately has exactly one rule, for the one
        # failure mode actually observed live — it must not touch any
        # other strategy value, even ones with their own unverified
        # risks (e.g. FORCE_NOT_ALLOWED, which the prompt already
        # discourages but doesn't forbid the parser from returning).
        strategy = ActionabilityStrategy(
            confidence=0.7,
            reasoning="ok",
            raw_response="{...}",
            reason=ActionabilityReason.RECEIVES_EVENTS,
            strategy=kind,
        )
        context = _context(collector_metadata={})

        result = validate_receives_events_strategy(strategy, context)

        assert result.strategy == kind
        assert result.corrected_by_policy is False
        assert result is strategy