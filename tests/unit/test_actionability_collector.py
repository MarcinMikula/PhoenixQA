"""
test_actionability_collector.py

Unit tests for ActionabilityCollector — RECEIVES_EVENTS context
gathering (mocked page.evaluate(), no live browser needed) and the
NotImplementedError guard for the four not-yet-built reasons. See
LEARNINGS.md "Sprint 6B (implementation) — ActionabilityCollector".
"""
from unittest.mock import MagicMock

import pytest

from phoenix.collector.collectors.actionability_collector import ActionabilityCollector
from phoenix.collector.failure_classifier import ActionabilityReason, ClassifiedFailure, FailureCategory


def _receives_events_classified(blocking_element='<div id="overlay"></div>'):
    return ClassifiedFailure(
        category=FailureCategory.ACTIONABILITY,
        action="click",
        locator_resolved=True,
        actionability_reason=ActionabilityReason.RECEIVES_EVENTS,
        blocking_element=blocking_element,
        raw_message="Locator.click: Timeout 200ms exceeded...",
    )


@pytest.mark.unit
class TestActionabilityCollectorReceivesEvents:
    def test_gathers_target_and_blocker_context_from_dom_probe(self):
        page = MagicMock()
        page.url = "http://localhost:5173/"
        page.evaluate.return_value = {
            "target_outer_html": '<button data-testid="btn-login">Log in</button>',
            "target_bounding_box": {"x": 10, "y": 20, "width": 100, "height": 40},
            "blocker_from_dom_probe": {
                "outer_html": '<div id="overlay"></div>',
                "bounding_box": {"x": 0, "y": 0, "width": 1280, "height": 720},
                "computed_style": {
                    "position": "fixed",
                    "zIndex": "9999",
                    "pointerEvents": "auto",
                    "opacity": "1",
                    "display": "block",
                    "visibility": "visible",
                },
            },
        }

        collector = ActionabilityCollector(page)
        classified = _receives_events_classified()
        context = collector.collect(
            "[data-testid='btn-login']", Exception("timeout"), "click", classified
        )

        assert context.category == FailureCategory.ACTIONABILITY
        assert context.actionability_reason == ActionabilityReason.RECEIVES_EVENTS
        assert context.collector_metadata["blocking_element_from_call_log"] == '<div id="overlay"></div>'
        assert context.collector_metadata["target_outer_html"] == '<button data-testid="btn-login">Log in</button>'
        assert context.collector_metadata["blocking_element_outer_html"] == '<div id="overlay"></div>'
        assert context.collector_metadata["blocking_element_computed_style"]["pointerEvents"] == "auto"
        assert "overlay" in context.dom_snapshot

    def test_animation_and_transition_style_pass_through_for_policy_validation(self):
        # actionability_policy.py's WAIT_AND_RETRY guardrail depends
        # directly on these two fields existing in collector_metadata —
        # a regression here would silently make that policy's "positive
        # evidence" branch permanently unreachable. See
        # LEARNINGS.md "Sprint 6B — deterministic policy guardrail".
        page = MagicMock()
        page.url = "http://localhost:5173/"
        page.evaluate.return_value = {
            "target_outer_html": '<button data-testid="btn-login">Log in</button>',
            "target_bounding_box": {"x": 10, "y": 20, "width": 100, "height": 40},
            "blocker_from_dom_probe": {
                "outer_html": '<div class="toast">Saving...</div>',
                "bounding_box": {"x": 0, "y": 0, "width": 200, "height": 40},
                "computed_style": {
                    "position": "fixed",
                    "zIndex": "10",
                    "pointerEvents": "auto",
                    "opacity": "1",
                    "display": "block",
                    "visibility": "visible",
                    "animationName": "fade-out",
                    # transition-property's real CSS default is "all",
                    # not "none" — see actionability_policy.py's
                    # regression test for why this distinction matters.
                    "transitionProperty": "all",
                },
            },
        }

        collector = ActionabilityCollector(page)
        classified = _receives_events_classified(blocking_element='<div class="toast">Saving...</div>')
        context = collector.collect(
            "[data-testid='btn-login']", Exception("timeout"), "click", classified
        )

        style = context.collector_metadata["blocking_element_computed_style"]
        assert style["animationName"] == "fade-out"
        assert style["transitionProperty"] == "all"

    def test_two_confirmations_can_be_compared_when_dom_probe_finds_nothing(self):
        # Edge case: the call log named a blocker, but by the time the
        # collector's own probe runs, elementFromPoint() finds the
        # target itself (e.g. a transient overlay that's since gone).
        # The collector must not crash — it just has one source instead
        # of two, and says so honestly rather than fabricating agreement.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        page.evaluate.return_value = {
            "target_outer_html": '<button data-testid="btn-login">Log in</button>',
            "target_bounding_box": {"x": 10, "y": 20, "width": 100, "height": 40},
            "blocker_from_dom_probe": None,
        }

        collector = ActionabilityCollector(page)
        classified = _receives_events_classified()
        context = collector.collect(
            "[data-testid='btn-login']", Exception("timeout"), "click", classified
        )

        assert context.collector_metadata["blocking_element_from_call_log"] == '<div id="overlay"></div>'
        assert "blocking_element_outer_html" not in context.collector_metadata
        assert "no independent confirmation" in context.dom_snapshot


@pytest.mark.unit
class TestActionabilityCollectorUnimplementedReasons:
    @pytest.mark.parametrize(
        "reason",
        [
            ActionabilityReason.VISIBLE,
            ActionabilityReason.ENABLED,
            ActionabilityReason.EDITABLE,
            ActionabilityReason.STABLE,
        ],
    )
    def test_raises_not_implemented_for_other_reasons(self, reason):
        page = MagicMock()
        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="fill",
            locator_resolved=True,
            actionability_reason=reason,
            raw_message="...",
        )

        with pytest.raises(NotImplementedError, match=reason.value):
            collector.collect("#target", Exception("timeout"), "fill", classified)

        # No DOM evaluation should be attempted for a reason with no
        # implemented strategy — fail before touching the page.
        page.evaluate.assert_not_called()