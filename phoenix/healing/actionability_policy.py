"""
actionability_policy.py

Deterministic policy guardrail sitting between an LLM's raw
ActionabilityStrategy proposal and anything that would ever act on it.

WHY THIS EXISTS — a real finding, not a precaution. See LEARNINGS.md
"Confirmatory re-runs resolve A vs B" and "actionability_prompt.py
revised": with temperature/seed pinned (removing sampling as a
variable) and a revised prompt (explicit self-consistency instruction,
corrected few-shot examples), llama3.2 STILL, deterministically,
proposed `wait_and_retry` for a blocker it had itself correctly
described — in its own `reasoning` field, in the same response — as
"persistent" and having "no dismiss affordance." Prompt engineering
alone was not sufficient: the model complied with identifying the
relevant FACTS but not with the RULE connecting those facts to a
decision. This module is the direct architectural response, per direct
discussion: "LLM may propose. PhoenixQA validates."

WHY THIS VALIDATES AGAINST collector_metadata, NOT reasoning TEXT — this
was a deliberate, explicit rejection of the more obvious first idea
(a keyword check against the model's reasoning string, e.g. searching
for "persistent" or "not transient"). That approach is fragile in
exactly the way natural language always is: the same judgment could be
phrased a dozen ways ("long-lived", "won't disappear", "sticking
around", in English or otherwise), and a keyword-matching validator
would be chasing phrasings indefinitely — itself a small, brittle
LLM-output parser living inside the codebase. `collector_metadata` is
structured, deterministic data gathered by ActionabilityCollector
directly from the DOM — validating against it means validating against
the one part of this pipeline that isn't natural language at all.

SCOPE — Sprint 6B: RECEIVES_EVENTS only, ONE rule. Not a general-purpose
validator for all five ActionabilityReason values, which don't have
collectors yet (see actionability_collector.py) — designing a general
rule set before a second reason exists to generalize from would be
guessing, same "one vertical slice at a time" discipline this project
has applied throughout Sprint 6.
"""
from dataclasses import replace

from phoenix.ai.base_provider import HealingContext
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind

# CSS computed-style values that constitute genuine POSITIVE evidence a
# blocker is animating / transitioning right now — as opposed to merely
# being present (position/zIndex/pointerEvents/opacity/display/visibility,
# which describe WHERE and WHETHER something blocks, not whether it is
# expected to go away on its own). "none" is the browser's own default
# for both properties when nothing is defined — anything else is a real,
# structural signal, not an inference from prose.
_NO_ANIMATION = "none"


def validate_receives_events_strategy(
    strategy: ActionabilityStrategy, context: HealingContext
) -> ActionabilityStrategy:
    """
    The one rule this module currently enforces: WAIT_AND_RETRY is only
    allowed when collector_metadata shows positive evidence the blocker
    is actually animating or transitioning. Without that evidence, a
    WAIT_AND_RETRY proposal is corrected to NO_SAFE_RECOVERY — not
    because the model's reasoning was necessarily wrong in every case,
    but because PhoenixQA has no deterministic basis to trust a "wait"
    action against a blocker with no structural sign it will change.

    Every other strategy value (DISMISS_BLOCKER, NO_SAFE_RECOVERY,
    SCROLL_INTO_VIEW, FORCE_NOT_ALLOWED) passes through unmodified —
    this policy has exactly one rule, for exactly one failure mode
    actually observed in live testing. It does not attempt to validate
    DISMISS_BLOCKER's blocking_element against the DOM, for example —
    that would be a real, separate policy to design later if evidence
    ever shows it's needed, not something to guess at now.

    Returns a NEW ActionabilityStrategy (dataclasses.replace) rather
    than mutating the argument in place — a caller that already logged
    or captured the original, uncorrected proposal (e.g. OllamaProvider's
    DEBUG log of the model's raw output) keeps that record intact; this
    function's return value is unambiguously the corrected, policy-safe
    version.
    """
    if strategy.strategy != ActionabilityStrategyKind.WAIT_AND_RETRY:
        return strategy

    if _has_positive_transient_evidence(context):
        return strategy

    return replace(
        strategy,
        strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
        corrected_by_policy=True,
        original_strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
        policy_reason=(
            "WAIT_AND_RETRY requires positive evidence in collector_metadata "
            "that the blocker is transient (an active CSS animation or "
            "transition). No such evidence was found — the blocker's "
            "computed style showed no animation/transition, or no blocker "
            "computed style was captured at all."
        ),
    )


def _has_positive_transient_evidence(context: HealingContext) -> bool:
    metadata = context.collector_metadata or {}
    computed_style = metadata.get("blocking_element_computed_style")
    if not isinstance(computed_style, dict):
        # No DOM-probe confirmation of the blocker at all (see
        # ActionabilityCollector — this happens when elementFromPoint()
        # found nothing beyond the target itself). No computed style
        # means no evidence, not an assumption either way.
        return False

    animation_name = computed_style.get("animationName")
    transition_property = computed_style.get("transitionProperty")

    has_animation = bool(animation_name) and animation_name != _NO_ANIMATION
    has_transition = bool(transition_property) and transition_property != _NO_ANIMATION
    return has_animation or has_transition