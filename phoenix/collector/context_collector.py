"""
context_collector.py
Gathers DOM snapshot, screenshot, console logs, network errors on failure.
TODO Sprint 2: implement full collection.
"""
from playwright.sync_api import Page
from phoenix.ai.base_provider import HealingContext


class ContextCollector:
    def __init__(self, page: Page):
        self.page = page

    def collect(self, broken_selector: str, error_message: str, original_code: str) -> HealingContext:
        raise NotImplementedError("ContextCollector — implement in Sprint 2")
