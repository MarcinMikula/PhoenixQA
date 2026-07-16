"""
base_collector.py

Common interface for per-FailureCategory context collectors, per the
Sprint 6 pre-coding decision (Decision #2) recorded in LEARNINGS.md —
mirrors provider_factory.py's existing pattern for AI providers.
ContextCollector routes to a concrete subclass based on
ClassifiedFailure.category; each subclass owns the collection strategy
for exactly one category.
"""
from abc import ABC, abstractmethod

from playwright.sync_api import Page

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.failure_classifier import ClassifiedFailure


class BaseContextCollector(ABC):
    def __init__(self, page: Page):
        self.page = page

    @abstractmethod
    def collect(
        self,
        broken_selector: str,
        error: Exception,
        original_code: str,
        classified: ClassifiedFailure,
    ) -> HealingContext:
        """Gather everything the LLM needs to diagnose and fix this specific failure."""
        raise NotImplementedError