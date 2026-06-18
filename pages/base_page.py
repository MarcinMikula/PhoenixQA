"""
base_page.py
BasePage for PhoenixQA — mirrors qa-automation-framework BasePage.
Adds self-healing hooks: on Playwright failure, calls Healer before giving up.
Healing is opt-in per call via healing=True flag.
"""
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
from config.settings import Settings


class BasePage:
    def __init__(self, page: Page, settings: Settings = None):
        self.page = page
        self.settings = settings or Settings()
        self.timeout = self.settings.default_timeout

    def navigate(self, url: str):
        self.page.goto(url)

    def click(self, selector: str, healing: bool = False):
        try:
            self.page.locator(selector).click(timeout=self.timeout)
        except PlaywrightTimeout as e:
            if healing:
                # TODO Sprint 4:
                # healed = self.healer.attempt_heal(selector, e, "click")
                # self.page.locator(healed).click(timeout=self.timeout)
                raise NotImplementedError("Healing not yet implemented — Sprint 4")
            raise

    def fill(self, selector: str, value: str, healing: bool = False):
        try:
            self.page.locator(selector).fill(value)
        except PlaywrightTimeout as e:
            if healing:
                raise NotImplementedError("Healing not yet implemented — Sprint 4")
            raise

    def get_text(self, selector: str) -> str:
        return self.page.locator(selector).inner_text()

    def is_visible(self, selector: str) -> bool:
        return self.page.locator(selector).is_visible()

    def wait_for_url(self, url_pattern: str):
        self.page.wait_for_url(url_pattern, timeout=self.timeout)
