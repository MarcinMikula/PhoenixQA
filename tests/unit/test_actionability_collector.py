"""
test_actionability_collector.py

Unit tests for ActionabilityCollector — RECEIVES_EVENTS and VISIBLE
context gathering (mocked page.evaluate(), no live browser needed) and
the NotImplementedError guard for the three not-yet-built reasons. See
LEARNINGS.md "Sprint 6B (implementation) — ActionabilityCollector" and
"Sprint 6B — second ActionabilityReason".
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
class TestActionabilityCollectorVisible:
    def test_gathers_target_context_with_no_state_change(self):
        # The PERMANENT-mode shape: identical state at t0 and t1 — no
        # observed change, so no evidence of transience. Ground truth:
        # no_safe_recovery.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot = {
            "target_outer_html": '<input data-testid="password-x7f2" type="password">',
            "visibility": "hidden", "display": "block", "opacity": "1",
            "bounding_box": {"x": 10, "y": 60, "width": 200, "height": 30},
        }
        page.evaluate.side_effect = [snapshot, dict(snapshot)]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="fill",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.VISIBLE,
            raw_message="Locator.fill: ... element is not visible",
        )
        context = collector.collect(
            "[data-testid='password-x7f2']", Exception("timeout"), "fill", classified
        )

        assert context.category == FailureCategory.ACTIONABILITY
        assert context.actionability_reason == ActionabilityReason.VISIBLE
        assert context.collector_metadata["target_outer_html"].startswith("<input")
        assert context.collector_metadata["target_state_changed_during_observation"] is False
        assert "not visible" in context.dom_snapshot
        # A real wall-clock wait must actually happen between the two
        # snapshots — this IS the mechanism that makes the evidence
        # temporal rather than declarative.
        page.wait_for_timeout.assert_called_once()

    def test_gathers_target_context_with_a_real_state_change(self):
        # The TRANSIENT-mode shape: visibility genuinely flips between
        # t0 and t1 — real, observed evidence. Ground truth:
        # wait_and_retry.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot_t0 = {
            "target_outer_html": '<input data-testid="password-x7f2" type="password">',
            "visibility": "hidden", "display": "block", "opacity": "1",
            "bounding_box": {"x": 10, "y": 60, "width": 200, "height": 30},
        }
        snapshot_t1 = {**snapshot_t0, "visibility": "visible"}
        page.evaluate.side_effect = [snapshot_t0, snapshot_t1]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="fill",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.VISIBLE,
            raw_message="Locator.fill: ... element is not visible",
        )
        context = collector.collect(
            "[data-testid='password-x7f2']", Exception("timeout"), "fill", classified
        )

        assert context.collector_metadata["target_state_changed_during_observation"] is True
        assert context.collector_metadata["target_state_t0"]["visibility"] == "hidden"
        assert context.collector_metadata["target_state_t1"]["visibility"] == "visible"

    def test_bounding_box_size_change_alone_counts_as_a_state_change(self):
        # An expanding accordion/section might never flip
        # visibility/display/opacity at all, only its rendered size —
        # that must still count as observed evidence of change.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot_t0 = {
            "target_outer_html": "<div>", "visibility": "visible",
            "display": "block", "opacity": "1",
            "bounding_box": {"x": 0, "y": 0, "width": 100, "height": 0},
        }
        snapshot_t1 = {
            **snapshot_t0,
            "bounding_box": {"x": 0, "y": 0, "width": 100, "height": 40},
        }
        page.evaluate.side_effect = [snapshot_t0, snapshot_t1]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="fill",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.VISIBLE,
            raw_message="...",
        )
        context = collector.collect("#x", Exception("timeout"), "fill", classified)

        assert context.collector_metadata["target_state_changed_during_observation"] is True

    def test_element_found_then_disappearing_counts_as_a_state_change(self):
        # The asymmetric missing-snapshot case: found at t0, gone by
        # t1 (e.g. removed from the DOM entirely between checks). A
        # real, observable difference — correctly True. Never directly
        # tested before this pass; caught while writing ENABLED's
        # mirror of this same logic and realizing VISIBLE's own
        # docstring claim about this case had no test backing it either
        # way.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot_t0 = {
            "target_outer_html": "<div>", "visibility": "visible",
            "display": "block", "opacity": "1",
            "bounding_box": {"x": 0, "y": 0, "width": 100, "height": 40},
        }
        page.evaluate.side_effect = [snapshot_t0, None]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="fill",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.VISIBLE,
            raw_message="...",
        )
        context = collector.collect("#x", Exception("timeout"), "fill", classified)

        assert context.collector_metadata["target_state_changed_during_observation"] is True

    def test_both_snapshots_missing_is_not_read_as_a_state_change(self):
        # The symmetric missing-snapshot case — see the corrected
        # docstring on _state_changed() for the full reasoning: found
        # at NEITHER point means there was never a state to observe
        # changing, correctly False, not folded into the asymmetric
        # case's "changed" reading. Never directly tested before this
        # pass.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        page.evaluate.side_effect = [None, None]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="fill",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.VISIBLE,
            raw_message="...",
        )
        context = collector.collect("#x", Exception("timeout"), "fill", classified)

        assert context.collector_metadata["target_state_changed_during_observation"] is False

    def test_no_dom_probe_or_blocker_fields_for_visible(self):
        # VISIBLE has no separate blocker concept — confirms the
        # collector doesn't invent blocking_element_* keys for a reason
        # that has no such thing, which would be misleading to a future
        # prompt reading collector_metadata.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot = {
            "target_outer_html": "<input>", "visibility": "hidden",
            "display": "block", "opacity": "1",
            "bounding_box": {"x": 0, "y": 0, "width": 10, "height": 10},
        }
        page.evaluate.side_effect = [snapshot, dict(snapshot)]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="fill",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.VISIBLE,
            raw_message="...",
        )
        context = collector.collect("#x", Exception("timeout"), "fill", classified)

        assert "blocking_element_outer_html" not in context.collector_metadata
        assert "blocking_element_from_call_log" not in context.collector_metadata


@pytest.mark.unit
class TestActionabilityCollectorEnabled:
    def test_gathers_target_context_with_no_state_change(self):
        # The PERMANENT-mode shape: still disabled at both t0 and t1 —
        # no observed change. Ground truth: no_safe_recovery.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot = {
            "target_outer_html": '<button data-testid="btn-login-x7f2" disabled="">Log in</button>',
            "disabled": True,
        }
        page.evaluate.side_effect = [snapshot, dict(snapshot)]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="click",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.ENABLED,
            raw_message="Locator.click: ... element is not enabled",
        )
        context = collector.collect(
            "[data-testid='btn-login-x7f2']", Exception("timeout"), "click", classified
        )

        assert context.category == FailureCategory.ACTIONABILITY
        assert context.actionability_reason == ActionabilityReason.ENABLED
        assert context.collector_metadata["target_outer_html"].startswith("<button")
        assert context.collector_metadata["target_state_changed_during_observation"] is False
        assert "not enabled" in context.dom_snapshot
        # Same temporal-evidence mechanism as VISIBLE — a real
        # wall-clock wait must happen between the two snapshots.
        page.wait_for_timeout.assert_called_once()

    def test_gathers_target_context_with_a_real_state_change(self):
        # The TRANSIENT-mode shape: disabled genuinely flips from True
        # to False between t0 and t1 — real, observed evidence. Ground
        # truth: wait_and_retry.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot_t0 = {
            "target_outer_html": '<button data-testid="btn-login-x7f2" disabled="">Log in</button>',
            "disabled": True,
        }
        snapshot_t1 = {**snapshot_t0, "disabled": False}
        page.evaluate.side_effect = [snapshot_t0, snapshot_t1]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="click",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.ENABLED,
            raw_message="Locator.click: ... element is not enabled",
        )
        context = collector.collect(
            "[data-testid='btn-login-x7f2']", Exception("timeout"), "click", classified
        )

        assert context.collector_metadata["target_state_changed_during_observation"] is True
        assert context.collector_metadata["target_state_t0"]["disabled"] is True
        assert context.collector_metadata["target_state_t1"]["disabled"] is False

    def test_element_found_then_disappearing_counts_as_a_state_change(self):
        # Mirrors VISIBLE's equivalent test — the asymmetric
        # missing-snapshot case (found at t0, gone by t1) is a real,
        # observable difference, correctly True.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot_t0 = {
            "target_outer_html": '<button data-testid="btn-login-x7f2">Log in</button>',
            "disabled": True,
        }
        page.evaluate.side_effect = [snapshot_t0, None]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="click",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.ENABLED,
            raw_message="...",
        )
        context = collector.collect("#x", Exception("timeout"), "click", classified)

        assert context.collector_metadata["target_state_changed_during_observation"] is True

    def test_both_snapshots_missing_is_not_read_as_a_state_change(self):
        # Caught while writing this test — the docstring on the
        # original VISIBLE method this mirrors overstated "missing
        # snapshots are treated as changed" as one blanket rule; the
        # ACTUAL (and semantically correct) behavior distinguishes
        # "found at one point, not the other" (True — a real
        # difference) from "found at NEITHER point" (False — there was
        # never a state to observe changing; waiting longer wouldn't
        # materialize an element that was never found at all). This
        # test pins down the second case specifically, now that the
        # docstring accurately describes it instead of overclaiming.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        page.evaluate.side_effect = [None, None]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="click",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.ENABLED,
            raw_message="...",
        )
        context = collector.collect("#x", Exception("timeout"), "click", classified)

        assert context.collector_metadata["target_state_changed_during_observation"] is False

    def test_no_dom_probe_or_blocker_fields_for_enabled(self):
        # ENABLED has no separate blocker concept, same as VISIBLE —
        # confirms the collector doesn't invent blocking_element_* keys.
        page = MagicMock()
        page.url = "http://localhost:5173/"
        snapshot = {"target_outer_html": "<button>", "disabled": True}
        page.evaluate.side_effect = [snapshot, dict(snapshot)]

        collector = ActionabilityCollector(page)
        classified = ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action="click",
            locator_resolved=True,
            actionability_reason=ActionabilityReason.ENABLED,
            raw_message="...",
        )
        context = collector.collect("#x", Exception("timeout"), "click", classified)

        assert "blocking_element_outer_html" not in context.collector_metadata
        assert "blocking_element_from_call_log" not in context.collector_metadata


@pytest.mark.unit
class TestActionabilityCollectorUnimplementedReasons:
    @pytest.mark.parametrize(
        "reason",
        [
            # ENABLED removed from this list (Sprint 8) — it's now
            # implemented, see TestActionabilityCollectorEnabled below.
            # Only EDITABLE/STABLE remain genuinely unimplemented.
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