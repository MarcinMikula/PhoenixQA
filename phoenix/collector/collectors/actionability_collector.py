"""
actionability_collector.py

Gathers context for FailureCategory.ACTIONABILITY. Three reasons have a
real collection strategy: RECEIVES_EVENTS (Sprint 6B, chosen first for
the richest signal — Playwright's call log names a specific blocking
element), VISIBLE (Sprint 6B, second reason — chosen next because it's
the cleanest way to test the OTHER direction of
actionability_policy.py's guardrail: does it correctly ALLOW
wait_and_retry when real evidence supports it, not just correctly BLOCK
it when evidence is absent), and ENABLED (Sprint 8, third reason —
chosen next because it reuses VISIBLE's temporal-evidence model
directly: "disabled → enabled" is the same SHAPE of observed state
change as "hidden → visible," just a different property). See
LEARNINGS.md "Sprint 6B (implementation) — ActionabilityCollector",
"Sprint 6B — second ActionabilityReason", and "Sprint 8 — third
ActionabilityReason (ENABLED)" for the full reasoning, including why
EDITABLE and STABLE remain deliberately NOT chosen yet (EDITABLE:
lower real-world realism than ENABLED per direct discussion; STABLE:
no deterministic Chaos App mechanism exists for it).

The remaining two reasons (EDITABLE, STABLE) raise NotImplementedError
— same convention as every other declared-but-not-yet-built path in
this project.

RECEIVES_EVENTS gets TWO independent confirmations of the blocker, not
just one:
  1. Playwright's own call log (classified.blocking_element, already
     parsed by failure_classifier.py from the "intercepts pointer
     events" line).
  2. An independent DOM probe via document.elementFromPoint() at the
     target element's center — deliberately NOT trusting the call log
     text alone, since it's Playwright's unversioned diagnostic wording
     (see Gap #13), not a stable API. If the two ever disagree, a future
     prompt has both to reconcile rather than one unverified source.

VISIBLE has NO separate blocker to confirm — Playwright's own message
for this reason is just "element is not visible," naming nothing else
(confirmed against the real captured call log in
tests/unit/test_failure_classifier.py, which uses a fill() action, not
click()). The evidence gathered is entirely about the TARGET element's
own state — no DOM probe needed, no ancestor walk (deliberately out of
scope for this slice — see LEARNINGS.md for why walking up the DOM for
a hiding ancestor was considered and deferred).

VISIBLE'S EVIDENCE IS TEMPORAL, NOT DECLARATIVE — a deliberate design
correction made during this slice, per direct discussion, before
RECEIVES_EVENTS' approach was reused unchanged. RECEIVES_EVENTS'
existing "positive evidence" (animationName/transitionProperty
declared in computed style) is really only evidence of ANIMATION
CAPABILITY, not evidence that a change is actually happening or will
resolve the failure — a genuinely raised concern: `animation-name:
pulse; animation-iteration-count: infinite` declares an animation that
will animate forever and never make anything newly actionable;
`transition-property: opacity` only says opacity WOULD transition IF
it changed, not that it is currently changing. For VISIBLE, this
collector instead takes TWO real snapshots of the target's state
(visibility/display/opacity/bounding box), separated by a genuine
wall-clock wait (`_VISIBLE_OBSERVATION_WINDOW_MS`), and the evidence
`actionability_policy.py` checks is whether the state ACTUALLY CHANGED
between them — an observed fact, not a declared capability. See
LEARNINGS.md "Sprint 6B — second ActionabilityReason" for the full
reasoning and the explicit decision NOT to retrofit RECEIVES_EVENTS in
the same commit (one design change per slice; RECEIVES_EVENTS' weaker
evidence is a documented, tracked limitation, not silently left as
though it were fine).

KNOWN SIMPLIFICATION, stated rather than hidden: two snapshots with one
fixed observation window, not the fuller t0/t1/t2 polling-with-a-ceiling
design that would catch a wider range of real timing without hardcoding
a window length. Chosen for this first slice because it's the minimum
viable version of "observe, don't declare" — a real improvement over
RECEIVES_EVENTS' approach — without building a polling loop before
there's evidence one is actually needed. Tracked as explicit future
work, not forgotten scope.

ENABLED REUSES VISIBLE'S TEMPORAL MODEL, NOT A NEW ONE — decided per
direct discussion before writing any code for this reason. A disabled
button becoming enabled is the same SHAPE of fact as a hidden element
becoming visible: an observed change in a boolean-ish DOM property
across two snapshots, not a declared CSS capability the way
RECEIVES_EVENTS' evidence is. Two real snapshots of the target's
`disabled` property, separated by the SAME wall-clock wait duration as
VISIBLE (reusing `_VISIBLE_OBSERVATION_WINDOW_MS` rather than
inventing a second, arbitrarily-different constant for a mechanically
identical wait) — the evidence `actionability_policy.py` checks is
whether `disabled` actually flipped between them, an observed fact,
same as VISIBLE's `target_state_changed_during_observation`.
"""
from typing import Optional

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.collectors.base_collector import BaseContextCollector
from phoenix.collector.failure_classifier import ActionabilityReason, ClassifiedFailure

# How long to wait between the two VISIBLE snapshots. Set slightly
# longer than visibilityDelay.jsx's own default delayMs (1000ms) so a
# genuinely TRANSIENT element (Chaos App's default configuration) has
# actually flipped state by the time the second snapshot is taken —
# see the module docstring's "KNOWN SIMPLIFICATION" note for why a
# single fixed window, not adaptive polling, was chosen for this slice.
_VISIBLE_OBSERVATION_WINDOW_MS = 1200

_GATHER_RECEIVES_EVENTS_CONTEXT_JS = """
    ([selector]) => {
        const target = document.querySelector(selector);
        if (!target) return null;

        const rect = target.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        const topElement = document.elementFromPoint(x, y);

        const result = {
            target_outer_html: target.outerHTML,
            target_bounding_box: {
                x: rect.x, y: rect.y, width: rect.width, height: rect.height,
            },
            blocker_from_dom_probe: null,
        };

        // Only a real blocker if elementFromPoint() found something
        // OTHER than the target itself at its own center point.
        if (topElement && topElement !== target) {
            const style = window.getComputedStyle(topElement);
            const blockerRect = topElement.getBoundingClientRect();
            result.blocker_from_dom_probe = {
                outer_html: topElement.outerHTML,
                bounding_box: {
                    x: blockerRect.x, y: blockerRect.y,
                    width: blockerRect.width, height: blockerRect.height,
                },
                computed_style: {
                    position: style.position,
                    zIndex: style.zIndex,
                    pointerEvents: style.pointerEvents,
                    opacity: style.opacity,
                    display: style.display,
                    visibility: style.visibility,
                    animationName: style.animationName,
                    transitionProperty: style.transitionProperty,
                },
            };
        }

        return result;
    }
"""

_GATHER_VISIBLE_SNAPSHOT_JS = """
    ([selector]) => {
        // querySelector still finds a visibility:hidden element — it's
        // only removed from the DOM by display:none or actual removal,
        // neither of which applies here. getBoundingClientRect() still
        // reports real (non-zero) layout dimensions for a
        // visibility:hidden element too, since it's still laid out,
        // just not painted. Called TWICE from Python, separated by a
        // real wait — see _VISIBLE_OBSERVATION_WINDOW_MS.
        const target = document.querySelector(selector);
        if (!target) return null;

        const rect = target.getBoundingClientRect();
        const style = window.getComputedStyle(target);

        return {
            target_outer_html: target.outerHTML,
            visibility: style.visibility,
            display: style.display,
            opacity: style.opacity,
            bounding_box: {
                x: rect.x, y: rect.y, width: rect.width, height: rect.height,
            },
        };
    }
"""

_GATHER_ENABLED_SNAPSHOT_JS = """
    ([selector]) => {
        // .disabled is the DOM property Playwright's own "enabled"
        // actionability check reads — not the `disabled` HTML
        // attribute's presence/absence as a string, the live boolean
        // property (which stays correct even for elements where the
        // attribute can be set without a value, e.g. `<button disabled>`).
        // Called TWICE from Python, separated by a real wait — same
        // window as VISIBLE, see _VISIBLE_OBSERVATION_WINDOW_MS.
        const target = document.querySelector(selector);
        if (!target) return null;

        return {
            target_outer_html: target.outerHTML,
            disabled: target.disabled === true,
        };
    }
"""


class ActionabilityCollector(BaseContextCollector):
    def collect(
        self,
        broken_selector: str,
        error: Exception,
        original_code: str,
        classified: ClassifiedFailure,
    ) -> HealingContext:
        if classified.actionability_reason == ActionabilityReason.RECEIVES_EVENTS:
            return self._collect_receives_events_context(
                broken_selector, error, original_code, classified
            )

        if classified.actionability_reason == ActionabilityReason.VISIBLE:
            return self._collect_visible_context(
                broken_selector, error, original_code, classified
            )

        if classified.actionability_reason == ActionabilityReason.ENABLED:
            return self._collect_enabled_context(
                broken_selector, error, original_code, classified
            )

        reason_label = (
            classified.actionability_reason.value
            if classified.actionability_reason
            else "an unknown reason"
        )
        raise NotImplementedError(
            f"ActionabilityCollector has no collection strategy for '{reason_label}' "
            f"yet. Only RECEIVES_EVENTS, VISIBLE, and ENABLED are implemented — see "
            f"LEARNINGS.md 'Sprint 6B (implementation) — ActionabilityCollector' and "
            f"'Sprint 8 — third ActionabilityReason (ENABLED)'."
        )

    def _collect_receives_events_context(
        self,
        broken_selector: str,
        error: Exception,
        original_code: str,
        classified: ClassifiedFailure,
    ) -> HealingContext:
        probe = self.page.evaluate(_GATHER_RECEIVES_EVENTS_CONTEXT_JS, [broken_selector])

        collector_metadata: dict = {
            "blocking_element_from_call_log": classified.blocking_element,
        }

        if probe:
            collector_metadata["target_outer_html"] = probe.get("target_outer_html")
            collector_metadata["target_bounding_box"] = probe.get("target_bounding_box")

            blocker = probe.get("blocker_from_dom_probe")
            if blocker:
                collector_metadata["blocking_element_outer_html"] = blocker.get("outer_html")
                collector_metadata["blocking_element_bounding_box"] = blocker.get("bounding_box")
                collector_metadata["blocking_element_computed_style"] = blocker.get("computed_style")

        dom_snapshot = self._format_receives_events_snapshot(classified, collector_metadata)

        return HealingContext(
            broken_selector=broken_selector,
            error_message=str(error),
            dom_snapshot=dom_snapshot,
            page_url=self.page.url,
            original_code=original_code,
            category=classified.category,
            actionability_reason=classified.actionability_reason,
            collector_metadata=collector_metadata,
            screenshot_path=None,
        )

    def _collect_visible_context(
        self,
        broken_selector: str,
        error: Exception,
        original_code: str,
        classified: ClassifiedFailure,
    ) -> HealingContext:
        snapshot_t0 = self.page.evaluate(_GATHER_VISIBLE_SNAPSHOT_JS, [broken_selector])
        self.page.wait_for_timeout(_VISIBLE_OBSERVATION_WINDOW_MS)
        snapshot_t1 = self.page.evaluate(_GATHER_VISIBLE_SNAPSHOT_JS, [broken_selector])

        collector_metadata: dict = {
            "observation_window_ms": _VISIBLE_OBSERVATION_WINDOW_MS,
            "target_state_t0": snapshot_t0,
            "target_state_t1": snapshot_t1,
            "target_state_changed_during_observation": self._state_changed(
                snapshot_t0, snapshot_t1
            ),
        }
        if snapshot_t0:
            collector_metadata["target_outer_html"] = snapshot_t0.get("target_outer_html")
            collector_metadata["target_bounding_box"] = snapshot_t0.get("bounding_box")

        dom_snapshot = self._format_visible_snapshot(collector_metadata)

        return HealingContext(
            broken_selector=broken_selector,
            error_message=str(error),
            dom_snapshot=dom_snapshot,
            page_url=self.page.url,
            original_code=original_code,
            category=classified.category,
            actionability_reason=classified.actionability_reason,
            collector_metadata=collector_metadata,
            screenshot_path=None,
        )

    def _collect_enabled_context(
        self,
        broken_selector: str,
        error: Exception,
        original_code: str,
        classified: ClassifiedFailure,
    ) -> HealingContext:
        snapshot_t0 = self.page.evaluate(_GATHER_ENABLED_SNAPSHOT_JS, [broken_selector])
        self.page.wait_for_timeout(_VISIBLE_OBSERVATION_WINDOW_MS)
        snapshot_t1 = self.page.evaluate(_GATHER_ENABLED_SNAPSHOT_JS, [broken_selector])

        collector_metadata: dict = {
            "observation_window_ms": _VISIBLE_OBSERVATION_WINDOW_MS,
            "target_state_t0": snapshot_t0,
            "target_state_t1": snapshot_t1,
            "target_state_changed_during_observation": self._enabled_state_changed(
                snapshot_t0, snapshot_t1
            ),
        }
        if snapshot_t0:
            collector_metadata["target_outer_html"] = snapshot_t0.get("target_outer_html")

        dom_snapshot = self._format_enabled_snapshot(collector_metadata)

        return HealingContext(
            broken_selector=broken_selector,
            error_message=str(error),
            dom_snapshot=dom_snapshot,
            page_url=self.page.url,
            original_code=original_code,
            category=classified.category,
            actionability_reason=classified.actionability_reason,
            collector_metadata=collector_metadata,
            screenshot_path=None,
        )

    @staticmethod
    def _enabled_state_changed(snapshot_t0: Optional[dict], snapshot_t1: Optional[dict]) -> bool:
        """
        ENABLED's counterpart to _state_changed() — deliberately a
        SEPARATE method, not a reuse of _state_changed() with different
        arguments, since the two compare entirely different fields
        (visibility/display/opacity/bounding-box vs. a single `disabled`
        boolean) and conflating them into one method with optional
        branches would obscure which fields actually matter for which
        reason. Same missing-snapshot semantics as _state_changed(),
        corrected there in this same pass after being caught here first:
        found at ONE point but not the other is a real, observable
        difference (`True`); found at NEITHER point means there was
        never a state to observe changing at all, correctly `False`,
        not folded into the asymmetric case's "changed" reading.
        """
        if snapshot_t0 is None or snapshot_t1 is None:
            return snapshot_t0 != snapshot_t1
        return snapshot_t0.get("disabled") != snapshot_t1.get("disabled")

    @staticmethod
    def _format_enabled_snapshot(metadata: dict) -> str:
        """Same short-summary principle as _format_visible_snapshot."""
        target_html: Optional[str] = metadata.get("target_outer_html")
        t0 = metadata.get("target_state_t0")
        t1 = metadata.get("target_state_t1")
        changed = metadata.get("target_state_changed_during_observation")
        window_ms = metadata.get("observation_window_ms")

        return (
            f"Target element (exists in the DOM but is not enabled):\n"
            f"{target_html or '<!-- not found -->'}\n"
            f"---\n"
            f"Observed state at t0: {t0 or '<!-- not captured -->'}\n"
            f"Observed state at t1 (+{window_ms}ms): {t1 or '<!-- not captured -->'}\n"
            f"State changed during observation: {changed}"
        )

    @staticmethod
    def _state_changed(snapshot_t0: Optional[dict], snapshot_t1: Optional[dict]) -> bool:
        """
        The one deterministic fact actionability_policy.py's
        validate_visible_strategy() trusts: did the target's actual
        rendered state change between the two snapshots — not whether
        its CSS declares that it COULD. Compares visibility/display/
        opacity plus bounding-box dimensions (a width/height change
        alone, e.g. an expanding accordion, counts even if visibility
        itself hasn't flipped yet).

        Missing snapshots are handled by DISTINCT cases, not one blanket
        rule — caught while writing ENABLED's mirror of this method,
        where the distinction had never actually been tested: if the
        element was found at ONE point but not the other (e.g. removed
        from the DOM entirely between checks), that asymmetry IS a
        real, observable difference and correctly evaluates to `True`
        (`populated_dict != None`). If it was found at NEITHER point,
        there is no state to have changed at all — waiting longer
        wouldn't materialize an element that was never found in the
        first place, so this correctly evaluates to `False`
        (`None != None`) rather than being folded into "treated as
        changed" the way the asymmetric case is. The two cases are
        semantically different questions ("did something happen to a
        real element" vs. "was there ever anything to observe"), not
        the same fact stated two ways.
        """
        if snapshot_t0 is None or snapshot_t1 is None:
            return snapshot_t0 != snapshot_t1

        if (
            snapshot_t0.get("visibility") != snapshot_t1.get("visibility")
            or snapshot_t0.get("display") != snapshot_t1.get("display")
            or snapshot_t0.get("opacity") != snapshot_t1.get("opacity")
        ):
            return True

        box0 = snapshot_t0.get("bounding_box") or {}
        box1 = snapshot_t1.get("bounding_box") or {}
        return box0.get("width") != box1.get("width") or box0.get("height") != box1.get("height")

    @staticmethod
    def _format_receives_events_snapshot(classified: ClassifiedFailure, metadata: dict) -> str:
        """
        dom_snapshot stays a short, human-readable summary — the rich,
        structured data a future prompt will actually consume lives in
        HealingContext.collector_metadata, not crammed into this string.
        """
        target_html: Optional[str] = metadata.get("target_outer_html")
        blocker_html: Optional[str] = metadata.get("blocking_element_outer_html")

        return (
            f"Target element:\n{target_html or '<!-- not found -->'}\n"
            f"---\n"
            f"Blocking element (named by Playwright's call log): "
            f"{classified.blocking_element or '<!-- not named -->'}\n"
            f"Blocking element (independently confirmed via elementFromPoint()):\n"
            f"{blocker_html or '<!-- no independent confirmation — target may be the topmost element -->'}"
        )

    @staticmethod
    def _format_visible_snapshot(metadata: dict) -> str:
        """
        Same short-summary principle as _format_receives_events_snapshot,
        but there is no separate blocker to describe for VISIBLE — only
        the target's own state, observed twice.
        """
        target_html: Optional[str] = metadata.get("target_outer_html")
        t0 = metadata.get("target_state_t0")
        t1 = metadata.get("target_state_t1")
        changed = metadata.get("target_state_changed_during_observation")
        window_ms = metadata.get("observation_window_ms")

        return (
            f"Target element (exists in the DOM but is not visible):\n"
            f"{target_html or '<!-- not found -->'}\n"
            f"---\n"
            f"Observed state at t0: {t0 or '<!-- not captured -->'}\n"
            f"Observed state at t1 (+{window_ms}ms): {t1 or '<!-- not captured -->'}\n"
            f"State changed during observation: {changed}"
        )