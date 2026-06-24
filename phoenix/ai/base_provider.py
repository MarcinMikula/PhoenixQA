"""
base_provider.py
Abstract base class for all LLM providers.
Pattern mirrors defect-pilot — swap provider via env var, zero code changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from phoenix.collector.failure_classifier import FailureType


@dataclass
class HealingContext:
    """Everything the LLM needs to propose a selector fix."""
    broken_selector: str
    error_message: str
    dom_snapshot: str
    page_url: str
    original_code: str
    failure_type: FailureType
    screenshot_path: Optional[str] = None


@dataclass
class HealingProposal:
    """Structured LLM response — always JSON under the hood."""
    proposed_selector: str
    confidence: float
    reasoning: str
    alternative_selectors: list = field(default_factory=list)
    raw_response: str = ""


class BaseProvider(ABC):
    @abstractmethod
    def analyze_failure(self, context: HealingContext) -> HealingProposal:
        """Given failure context, propose a healed selector."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify provider is reachable before test run."""
        pass
