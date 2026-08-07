"""
actions.py

The HealingAction hierarchy — see LEARNINGS.md "Sprint 6B (decision)"
for the full reasoning, and "Sprint 6B (decision) — HealingAction
migration" for confirmation this was implemented as a narrow,
behavior-preserving refactor.

Replaces HealingProposal as the universal provider return shape.
SelectorReplacement is the FailureCategory.LOCATOR_RESOLUTION-specific
member — today's only live, end-to-end path. ActionabilityStrategy
(FailureCategory.ACTIONABILITY, RECEIVES_EVENTS only) is produced by
OllamaProvider (Sprint 6B) but still rejected outright by Healer — no
execution exists yet. RetryStrategy (the dormant FailureCategory.REFERENCE)
remains declared-only, same pattern as FailureType's original four
members in Sprint 2 — declared, not all implemented at once. Healer
explicitly rejects anything that isn't a SelectorReplacement rather than
silently mishandling it (see healer.py).
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from phoenix.collector.failure_classifier import ActionabilityReason


@dataclass
class HealingAction:
    """
    Common base for every kind of fix PhoenixQA can propose. confidence
    and reasoning are shared across all subtypes — a human or an
    Autonomous Mode policy always needs "how sure" and "why", regardless
    of whether the fix is a new selector or (once built) a wait/dismiss
    strategy.
    """
    confidence: float
    reasoning: str
    raw_response: str = ""


@dataclass
class SelectorReplacement(HealingAction):
    """
    FailureCategory.LOCATOR_RESOLUTION's action shape. Field names and
    meaning are unchanged from the old HealingProposal — only the type
    and its location moved.
    """
    proposed_selector: str = ""
    alternative_selectors: list = field(default_factory=list)


class ActionabilityStrategyKind(Enum):
    WAIT_AND_RETRY = "wait_and_retry"
    SCROLL_INTO_VIEW = "scroll_into_view"
    DISMISS_BLOCKER = "dismiss_blocker"
    FORCE_NOT_ALLOWED = "force_not_allowed"
    NO_SAFE_RECOVERY = "no_safe_recovery"


@dataclass
class ActionabilityStrategy(HealingAction):
    """
    FailureCategory.ACTIONABILITY's action shape — produced (RECEIVES_EVENTS
    only) by OllamaProvider, still rejected outright by Healer (no
    execution exists yet — see healer.py). `strategy` exists alongside
    `reason` because a single ActionabilityReason doesn't imply a single
    fix (VISIBLE alone could mean wait, scroll into view, expand a
    section, or dismiss an overlay) — see LEARNINGS.md "Sprint 6B
    (decision)".

    corrected_by_policy/original_strategy/policy_reason (Sprint 6B):
    populated by phoenix/healing/actionability_policy.py when a deterministic,
    evidence-based guardrail overrides the model's own proposed
    `strategy` — see that module's docstring for why this exists. Not
    filled in by the parser or the provider itself; the policy layer is
    the only writer. `corrected_by_policy=False` (the default) means
    `strategy` is exactly what the model proposed, unmodified.
    """
    reason: Optional[ActionabilityReason] = None
    strategy: Optional[ActionabilityStrategyKind] = None
    suggested_wait_ms: Optional[int] = None
    blocking_element: Optional[str] = None
    corrected_by_policy: bool = False
    original_strategy: Optional[ActionabilityStrategyKind] = None
    policy_reason: Optional[str] = None


@dataclass
class RetryStrategy(HealingAction):
    """
    FailureCategory.REFERENCE's action shape — dormant, see Gap #4.
    Declared, not implemented; no collector or provider produces this.
    """
    wait_ms: int = 0
    reacquire_locator: bool = True