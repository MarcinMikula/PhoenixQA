"""
actionability_collector.py

Gathers context for FailureCategory.ACTIONABILITY. Sprint 6B scope:
only ActionabilityReason.RECEIVES_EVENTS has a real collection strategy
— chosen first because it gives the richest, most deterministic signal
of the five reasons: Playwright's own call log names the specific
blocking element (unlike VISIBLE/ENABLED/EDITABLE/STABLE, which only
report a condition, not a culprit), and it's realistic and common in
production UIs (cookie banners, modals, sticky headers, loading
overlays, stale backdrops). See LEARNINGS.md "Sprint 6B
(implementation) — ActionabilityCollector" for the full reasoning,
including why STABLE was deliberately NOT chosen first (no deterministic
Chaos App mechanism exists for it yet, and Sprint 6A/6B both found
timing-based reproduction attempts unreliable).

The remaining four reasons raise NotImplementedError — same convention
as every other declared-but-not-yet-built path in this project.

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
"""
from typing import Optional

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.collectors.base_collector import BaseContextCollector
from phoenix.collector.failure_classifier import ActionabilityReason, ClassifiedFailure

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
                },
            };
        }

        return result;
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

        reason_label = (
            classified.actionability_reason.value
            if classified.actionability_reason
            else "an unknown reason"
        )
        raise NotImplementedError(
            f"ActionabilityCollector has no collection strategy for '{reason_label}' "
            f"yet. Only RECEIVES_EVENTS is implemented — see LEARNINGS.md "
            f"'Sprint 6B (implementation) — ActionabilityCollector'."
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

        dom_snapshot = self._format_dom_snapshot(classified, collector_metadata)

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
    def _format_dom_snapshot(classified: ClassifiedFailure, metadata: dict) -> str:
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