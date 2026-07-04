"""
base_page.py
BasePage for PhoenixQA — mirrors qa-automation-framework BasePage.
Adds self-healing hooks: on Playwright failure, calls Healer before giving up.
Healing is opt-in per call via healing=True flag.

Sprint 4: Healer is lazily constructed (only when healing is actually
needed) rather than always created in __init__ — most BasePage calls in
a typical test run never fail, so there's no reason to set up a Healer
(which constructs a provider + collector) on every single page object
instantiation. See _get_healer().

BUG FIX (found via Sprint 6A live verification attempt, see LEARNINGS.md):
click()/fill() previously let HealingRejectedError / HealingLimitExceededError
/ HealingFailedError propagate directly to pytest. healer.py's own
docstrings had always documented the intended behavior differently — "the
ORIGINAL Playwright error should surface to pytest, not a healing-internal
exception" — but that catch was never actually implemented here. In
practice this meant an autonomous rejection (e.g. a truncated LLM
response) reported a confusing "confidence 0.00 below policy threshold"
message instead of the real underlying TimeoutError with its call log,
even though the rich diagnosis (why healing failed, what was proposed)
was always available in healing_decisions.log for anyone who went
looking. Fixed by catching all three Healer exception types and
re-raising the ORIGINAL exception that triggered healing in the first
place — pytest now reports the same failure it always would have without
healing enabled at all, which is the documented contract.
"""
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
from config.settings import Settings
from phoenix.healing.healer import (
    HealingFailedError,
    HealingLimitExceededError,
    HealingRejectedError,
)

# Grouped once so click()/fill() don't each need their own 3-tuple —
# these three are exactly the "healing was attempted and did not produce
# a usable fix" family (see healer.py's three-exception-type design,
# Sprint 5 "Decision: three distinct exception types, not one"). Any
# OTHER exception raised out of attempt_heal() (there shouldn't be one —
# HealingFailedError is meant to wrap provider/pipeline crashes) is
# deliberately NOT caught here, so a genuinely unexpected bug in the
# healing pipeline itself is never silently swallowed as "just a failed
# heal."
_HEALING_DECLINED_EXCEPTIONS = (HealingRejectedError, HealingLimitExceededError, HealingFailedError)


class BasePage:
    def __init__(self, page: Page, settings: Settings = None):
        self.page = page
        self.settings = settings or Settings()
        self.timeout = self.settings.default_timeout
        self._healer = None  # lazily constructed, see _get_healer()

    def _get_healer(self):
        """
        Constructs the Healer on first actual use, not in __init__.
        Avoids paying the cost of provider/collector setup for every
        BasePage instance when most of them never hit a healing path.
        """
        if self._healer is None:
            from phoenix.healing.healer import Healer
            self._healer = Healer(self.page, self.settings)
        return self._healer

    def navigate(self, url: str):
        self.page.goto(url)

    def click(self, selector: str, healing: bool = False):
        try:
            self.page.locator(selector).click(timeout=self.timeout)
        except PlaywrightTimeout as e:
            if healing:
                try:
                    healed_selector = self._get_healer().attempt_heal(selector, e, "click")
                except _HEALING_DECLINED_EXCEPTIONS:
                    # Healing was attempted and did not produce a usable
                    # fix (rejected, budget exhausted, or the pipeline
                    # itself crashed) — the full "why" is already in
                    # healing_decisions.log. What pytest needs to report
                    # is the ORIGINAL failure, not a healing-internal one.
                    raise e
                # Retry with the healed selector — same test step, not a
                # restart. See healer.py module docstring for why this
                # is the confirmed flow.
                self.page.locator(healed_selector).click(timeout=self.timeout)
            else:
                raise

    def fill(self, selector: str, value: str, healing: bool = False):
        try:
            self.page.locator(selector).fill(value)
        except PlaywrightTimeout as e:
            if healing:
                try:
                    healed_selector = self._get_healer().attempt_heal(selector, e, "fill")
                except _HEALING_DECLINED_EXCEPTIONS:
                    raise e
                self.page.locator(healed_selector).fill(value)
            else:
                raise

    def get_text(self, selector: str) -> str:
        return self.page.locator(selector).inner_text()

    def is_visible(self, selector: str) -> bool:
        return self.page.locator(selector).is_visible()

    def wait_for_url(self, url_pattern: str):
        self.page.wait_for_url(url_pattern, timeout=self.timeout)