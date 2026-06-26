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
"""
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
from config.settings import Settings


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
                healed_selector = self._get_healer().attempt_heal(selector, e, "click")
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
                healed_selector = self._get_healer().attempt_heal(selector, e, "fill")
                self.page.locator(healed_selector).fill(value)
            else:
                raise

    def get_text(self, selector: str) -> str:
        return self.page.locator(selector).inner_text()

    def is_visible(self, selector: str) -> bool:
        return self.page.locator(selector).is_visible()

    def wait_for_url(self, url_pattern: str):
        self.page.wait_for_url(url_pattern, timeout=self.timeout)
