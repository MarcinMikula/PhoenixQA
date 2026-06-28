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


@dataclass
class ProviderResult:
    """
    Neutral metadata about a single analyze_failure() call — tokens and
    elapsed time only, NEVER a dollar cost (see LEARNINGS.md "Sprint 5 —
    Decision: budget in tokens/time, never in currency"). Model pricing
    changes over time; token counts don't. HealingBudget (Sprint 5)
    consumes these to enforce limits; converting to a price, if ever
    wanted, is the caller's job, not this codebase's.

    input_tokens/output_tokens are Optional because not every provider
    reports both reliably (e.g. Ollama's /api/generate gives eval_count
    for output but prompt_eval_count for input — both present in
    practice, but the field stays optional so a provider that genuinely
    can't report one doesn't have to fake a number).
    """
    proposal: HealingProposal
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    elapsed_ms: Optional[int] = None


class BaseProvider(ABC):
    @abstractmethod
    def analyze_failure(self, context: HealingContext) -> ProviderResult:
        """
        Given failure context, propose a healed selector. Returns a
        ProviderResult wrapping the HealingProposal alongside neutral
        token/timing metadata — NOT just the proposal alone, since
        Sprint 5's HealingBudget needs that metadata to enforce limits.
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify provider is reachable before test run."""
        pass
