"""
base_provider.py
Abstract base class for all LLM providers.
Pattern mirrors defect-pilot — swap provider via env var, zero code changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.actions import HealingAction


@dataclass
class HealingContext:
    """
    Everything the LLM needs to propose a fix — a selector replacement
    for FailureCategory.LOCATOR_RESOLUTION, or (once the prompt layer
    exists) an actionability recovery strategy for
    FailureCategory.ACTIONABILITY. See LEARNINGS.md "Sprint 6B
    (decision)" for why this is category + optional reason, not the
    single flat failure_type field this class had through Sprint 6A.

    collector_metadata (Sprint 6B — ActionabilityCollector) is a
    deliberately generic, optional bag for whatever extra structured
    data a given collector wants to attach, rather than hardcoding
    RECEIVES_EVENTS-specific (or any other single reason's) field names
    onto this shared dataclass. dom_snapshot stays a short,
    human-readable summary for any collector that wants one;
    collector_metadata carries the richer structured data (bounding
    boxes, computed styles, etc.) a future prompt will actually consume.
    Kept generic on purpose — the exact shape needed for STABLE or any
    other future reason isn't known yet, and hardcoding fields for one
    reason now would bias that design before there's evidence for it.
    """
    broken_selector: str
    error_message: str
    dom_snapshot: str
    page_url: str
    original_code: str
    category: FailureCategory
    actionability_reason: Optional[ActionabilityReason] = None
    collector_metadata: Optional[dict] = None
    screenshot_path: Optional[str] = None


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

    Sprint 6B (decision): `action: HealingAction` replaces the old
    `proposal: HealingProposal` — see phoenix/healing/actions.py. Today,
    every real provider still only ever produces a SelectorReplacement;
    Healer explicitly rejects anything else rather than assuming it's
    always a selector (see healer.py).
    """
    action: HealingAction
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    elapsed_ms: Optional[int] = None


class BaseProvider(ABC):
    @abstractmethod
    def analyze_failure(self, context: HealingContext) -> ProviderResult:
        """
        Given failure context, propose a fix. Returns a ProviderResult
        wrapping a HealingAction alongside neutral token/timing
        metadata — NOT just the action alone, since Sprint 5's
        HealingBudget needs that metadata to enforce limits.
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify provider is reachable before test run."""
        pass