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

SCOPE — originally RECEIVES_EVENTS only, ONE rule (Sprint 6B). Extended
to VISIBLE (Sprint 6B, second ActionabilityReason) once a second reason
actually existed to generalize from — deliberately not designed as a
general-purpose validator for all five ActionabilityReason values ahead
of that evidence, same "one vertical slice at a time" discipline this
project has applied throughout Sprint 6. Both reasons share the same
underlying PRINCIPLE (WAIT_AND_RETRY needs positive evidence before
being trusted) but deliberately NOT the same evidence STANDARD:
RECEIVES_EVENTS checks for a declared CSS animation/transition
capability; VISIBLE checks for an actually OBSERVED state change across
two real snapshots — a stronger standard adopted specifically for
VISIBLE, per direct discussion, once its weaker precedent was
recognized rather than copied forward unexamined. See
validate_visible_strategy()'s own docstring for the full reasoning,
including why RECEIVES_EVENTS was NOT retrofitted in the same slice.
"""
from dataclasses import replace

from phoenix.ai.base_provider import HealingContext
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind

# CSS computed-style values that constitute genuine POSITIVE evidence
# something is animating / transitioning right now — as opposed to
# merely being present (position/zIndex/pointerEvents/opacity/display/
# visibility, which describe WHERE and WHETHER something blocks or is
# hidden, not whether it is expected to change).
#
# The two properties have DIFFERENT CSS-spec default values, confirmed
# live (see LEARNINGS.md "Sprint 6B — live re-verification catches a
# real bug in the policy itself"): animation-name's initial value is
# "none", but transition-property's initial value is "all" — every
# plain, unstyled element in a real browser reports
# transitionProperty="all" via getComputedStyle(), NOT "none". The
# original implementation checked both against the single constant
# "none", so a real overlay's default "all" was wrongly read as
# positive evidence of an active transition — a false positive present
# in every element, that a mocked-value unit test (which happened to
# use "none" for both fields) could not have caught.
_NO_ANIMATION_NAME = "none"
_DEFAULT_TRANSITION_PROPERTY = "all"


def validate_receives_events_strategy(
    strategy: ActionabilityStrategy, context: HealingContext
) -> ActionabilityStrategy:
    """
    ActionabilityReason.RECEIVES_EVENTS: WAIT_AND_RETRY is only allowed
    when collector_metadata's blocking_element_computed_style shows
    positive evidence the BLOCKING ELEMENT is actually animating or
    transitioning. Without that evidence, a WAIT_AND_RETRY proposal is
    corrected to NO_SAFE_RECOVERY — not because the model's reasoning
    was necessarily wrong in every case, but because PhoenixQA has no
    deterministic basis to trust a "wait" action against a blocker with
    no structural sign it will change.

    Every other strategy value (DISMISS_BLOCKER, NO_SAFE_RECOVERY,
    SCROLL_INTO_VIEW, FORCE_NOT_ALLOWED) passes through unmodified —
    this rule covers exactly one failure mode actually observed in live
    testing. It does not attempt to validate DISMISS_BLOCKER's
    blocking_element against the DOM, for example — that would be a
    real, separate rule to design later if evidence ever shows it's
    needed, not something to guess at now.
    """
    return _validate_wait_and_retry(strategy, context, metadata_key="blocking_element_computed_style")


def validate_visible_strategy(
    strategy: ActionabilityStrategy, context: HealingContext
) -> ActionabilityStrategy:
    """
    ActionabilityReason.VISIBLE: same PRINCIPLE as RECEIVES_EVENTS
    (WAIT_AND_RETRY requires positive evidence), but a DELIBERATELY
    STRONGER evidence standard — per direct discussion, a genuine
    correction made during this reason's own slice, not carried over
    from RECEIVES_EVENTS unchanged.

    RECEIVES_EVENTS' evidence (see validate_receives_events_strategy)
    checks whether animation/transition is DECLARED in computed style —
    which is really evidence of CAPABILITY, not of an actual change in
    progress. A raised, valid concern: `animation-iteration-count:
    infinite` declares an animation that never resolves anything;
    `transition-property: opacity` only says opacity WOULD transition IF
    it changed, not that it currently is. VISIBLE's evidence instead
    comes from ActionabilityCollector taking two real snapshots of the
    target's state, separated by a genuine wait, and checking
    collector_metadata["target_state_changed_during_observation"] — an
    OBSERVED FACT (did visibility/display/opacity/bounding-box actually
    change), not a declared capability. See actionability_collector.py's
    module docstring for the full design and its own honestly-stated
    simplifications (a single fixed observation window, not adaptive
    polling).

    Deliberately NOT retrofitted onto RECEIVES_EVENTS in this same
    slice — one evidence-design change per slice, same discipline this
    project has applied throughout Sprint 6. RECEIVES_EVENTS' weaker,
    declaration-based evidence is a known, tracked limitation (see
    LEARNINGS.md and docs/gaps.md), not a silently accepted gap.
    """
    if strategy.strategy != ActionabilityStrategyKind.WAIT_AND_RETRY:
        return strategy

    metadata = context.collector_metadata or {}
    state_changed = metadata.get("target_state_changed_during_observation", False)

    if state_changed:
        return strategy

    return replace(
        strategy,
        strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
        corrected_by_policy=True,
        original_strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
        policy_reason=(
            "WAIT_AND_RETRY requires the target element's observed state "
            "(visibility/display/opacity/bounding box) to have actually "
            f"changed during collection (a {metadata.get('observation_window_ms', '?')}ms "
            "observation window) — no change was observed, so there is no "
            "basis to believe waiting longer would help."
        ),
    )


def _validate_wait_and_retry(
    strategy: ActionabilityStrategy, context: HealingContext, metadata_key: str
) -> ActionabilityStrategy:
    """
    Shared implementation for validate_receives_events_strategy() above
    — VISIBLE has its own, stronger evidence check
    (validate_visible_strategy(), see its docstring for why it does NOT
    share this implementation).
    Returns a NEW ActionabilityStrategy (dataclasses.replace) rather
    than mutating the argument in place — a caller that already logged
    or captured the original, uncorrected proposal (e.g. OllamaProvider's
    DEBUG log of the model's raw output) keeps that record intact; this
    function's return value is unambiguously the corrected, policy-safe
    version.
    """
    if strategy.strategy != ActionabilityStrategyKind.WAIT_AND_RETRY:
        return strategy

    metadata = context.collector_metadata or {}
    computed_style = metadata.get(metadata_key)

    if _has_positive_transient_evidence(computed_style):
        return strategy

    return replace(
        strategy,
        strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
        corrected_by_policy=True,
        original_strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
        policy_reason=(
            "WAIT_AND_RETRY requires positive evidence in collector_metadata "
            f"['{metadata_key}'] that this is actually transient (an active "
            "CSS animation or transition). No such evidence was found — the "
            "computed style showed no animation/transition, or none was "
            "captured at all."
        ),
    )


def _has_positive_transient_evidence(computed_style) -> bool:
    if not isinstance(computed_style, dict):
        # No computed style captured at all (e.g. RECEIVES_EVENTS' DOM
        # probe found nothing beyond the target itself — see
        # ActionabilityCollector). No computed style means no evidence,
        # not an assumption either way.
        return False

    animation_name = computed_style.get("animationName")
    transition_property = computed_style.get("transitionProperty")

    has_animation = bool(animation_name) and animation_name != _NO_ANIMATION_NAME
    has_transition = bool(transition_property) and transition_property not in (
        _DEFAULT_TRANSITION_PROPERTY,
        "none",
    )
    return has_animation or has_transition