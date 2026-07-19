"""
context_collector.py

Thin router over per-FailureCategory collectors, per the Sprint 6
pre-coding decision (Decision #2) recorded in LEARNINGS.md — mirrors
provider_factory.py's existing pattern for AI providers. Classifies the
failure via parse_playwright_call_log(), then delegates to the matching
collector.

FailureCategory.LOCATOR_RESOLUTION -> LocatorResolutionCollector (live
since Sprint 2, moved into its own module in the router split).
FailureCategory.ACTIONABILITY -> ActionabilityCollector (Sprint 6B —
only ActionabilityReason.RECEIVES_EVENTS implemented; the collector
itself raises NotImplementedError for the other four reasons, not this
router).
FailureCategory.REFERENCE and UNKNOWN still raise NotImplementedError
directly here — no ReferenceCollector exists at all, dormant per Gap #4.
"""
from playwright.sync_api import Page

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.collectors.actionability_collector import ActionabilityCollector
from phoenix.collector.collectors.locator_resolution_collector import LocatorResolutionCollector
from phoenix.collector.failure_classifier import FailureCategory, parse_playwright_call_log


class ContextCollector:
    def __init__(self, page: Page):
        self.page = page
        self._locator_resolution_collector = LocatorResolutionCollector(page)
        self._actionability_collector = ActionabilityCollector(page)

    def collect(self, broken_selector: str, error: Exception, original_code: str) -> HealingContext:
        """
        Main entry point — called from Healer (Sprint 4/5) when a
        Playwright action fails. Classifies the failure via
        parse_playwright_call_log(), then routes to the matching
        collector.
        """
        classified = parse_playwright_call_log(error)

        if classified.category == FailureCategory.LOCATOR_RESOLUTION:
            return self._locator_resolution_collector.collect(
                broken_selector, error, original_code, classified
            )

        if classified.category == FailureCategory.ACTIONABILITY:
            return self._actionability_collector.collect(
                broken_selector, error, original_code, classified
            )

        # REFERENCE (dormant, Gap #4) and UNKNOWN have no collector at
        # all yet. Explicit and loud, not a silent fallback that would
        # produce misleading context.
        raise NotImplementedError(
            f"ContextCollector has no collector for {classified.category.value} yet. "
            f"See LEARNINGS.md 'Sprint 6B (decision)'."
        )