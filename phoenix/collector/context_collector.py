"""
context_collector.py

Thin router over per-FailureCategory collectors, per the Sprint 6
pre-coding decision (Decision #2) recorded in LEARNINGS.md — mirrors
provider_factory.py's existing pattern for AI providers. Classifies the
failure via parse_playwright_call_log(), then delegates to the matching
collector.

Only FailureCategory.LOCATOR_RESOLUTION has a real collector
(collectors/locator_resolution_collector.py). ACTIONABILITY (5 reasons)
and the dormant REFERENCE category raise NotImplementedError here rather
than being half-built — see LEARNINGS.md "Sprint 6B (decision)".

This file was previously the single class containing all collection
logic directly; that logic moved into LocatorResolutionCollector
unchanged (see LEARNINGS.md "Sprint 6B (implementation)" for
confirmation this was a pure move — same tests, same assertions, still
passing, zero behavior change).
"""
from playwright.sync_api import Page

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.collectors.locator_resolution_collector import LocatorResolutionCollector
from phoenix.collector.failure_classifier import FailureCategory, parse_playwright_call_log


class ContextCollector:
    def __init__(self, page: Page):
        self.page = page
        self._locator_resolution_collector = LocatorResolutionCollector(page)

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

        # Only LOCATOR_RESOLUTION has a real collector so far.
        # ACTIONABILITY (5 reasons) and the dormant REFERENCE category
        # are declared in the model (see LEARNINGS.md "Sprint 6B
        # (decision)") but have no collector yet. Explicit and loud, not
        # a silent fallback that would produce misleading context.
        raise NotImplementedError(
            f"ContextCollector has no collector for {classified.category.value} yet. "
            f"Planned for a future sub-sprint (actionability_collector.py) — see LEARNINGS.md "
            f"'Sprint 6B (decision)'."
        )