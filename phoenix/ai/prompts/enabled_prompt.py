"""
enabled_prompt.py

Builds the system + user prompt for FailureCategory.ACTIONABILITY /
ActionabilityReason.ENABLED — a locator that resolved fine (the element
exists in the DOM, is visible, and is stable), but Playwright's own
actionability check reports it as not enabled (the `disabled` property
is set — common real causes: a submit button disabled until
client-side validation passes, disabled while an async save is in
flight, disabled until a required checkbox is ticked).

CATEGORICALLY THE SAME SHAPE AS visible_prompt.py, deliberately — per
direct discussion before writing any code for this reason.
"Disabled → enabled" is the same KIND of fact as "hidden → visible": an
observed change in a single DOM property across two real snapshots, not
a declared CSS capability the way RECEIVES_EVENTS' evidence is. This
prompt is visible_prompt.py's structure with `disabled` substituted for
visibility/display/opacity/bounding-box — not a fresh design, since the
underlying evidence question ("did the state ACTUALLY change between
t0 and t1, or are we being shown a CSS/attribute declaration that
merely COULD change") is identical.

Like VISIBLE, there is no separate "blocker" element here — the target
IS the thing that's wrong, not something else sitting in front of it.
The model only ever has ONE element's evidence to reason about.

EVIDENCE IS TEMPORAL, NOT DECLARATIVE — same principle as
visible_prompt.py, inherited rather than re-derived: the model is told
whether `disabled` was OBSERVED to flip across two real snapshots (see
phoenix/collector/collectors/actionability_collector.py's
_collect_enabled_context), not asked to infer anything from a CSS
transition/animation declaration (which wouldn't even apply to a plain
`disabled` boolean attribute the way it does for VISIBLE's
visibility/opacity).

SELF-CONSISTENCY INSTRUCTION carried over from visible_prompt.py for
the same reason it was carried over there from actionability_prompt.py
— a chance the model's decision-vs-diagnosis gap (Sprint 6B,
RECEIVES_EVENTS) doesn't recur on this evidence shape either, but
actionability_policy.py's validate_enabled_strategy() remains the
actual, deterministic gate regardless of what this prompt achieves on
its own.
"""
from phoenix.ai.base_provider import HealingContext

SYSTEM_PROMPT = """You are a test automation engineer's assistant. A Playwright test failed while trying to interact with an element that WAS found on the page, IS visible, and IS stable (the selector is correct and does not need to change) — but Playwright reports the element as NOT ENABLED. This is a test environment that intentionally disables elements (a submit button disabled until validation passes, disabled during an async save, disabled until a checkbox is ticked) to simulate real-world timing issues.

IMPORTANT: unlike a "selector not found" problem, there is nothing to rename here. The target element's selector is correct and must NOT be changed. Your job is to decide, from the element's own observed state, what recovery strategy makes sense — not to propose a new selector.

There is no separate "blocking element" here — Playwright is not telling you something else is in the way. The element itself is what is not enabled right now.

You will be given the element's `disabled` state observed TWICE — once immediately, and once again after a short real wait — rather than just a single snapshot or a CSS declaration. Whether the element's actual `disabled` state CHANGED between the two observations is the evidence that matters here.

HOW TO DECIDE — follow these steps in order:
1. Compare the element's observed `disabled` state at the first check (t0) against the second check (t1, after the wait).
2. If `disabled` ACTUALLY CHANGED from true to false between t0 and t1 — that is real evidence something is in progress (validation completing, a save finishing). Propose "wait_and_retry" with a suggested_wait_ms roughly matching how long you were told the observation window was.
3. If `disabled` did NOT change between t0 and t1 (still disabled at both, or already enabled at both — though the latter shouldn't occur, since this prompt is only used when Playwright's check failed), propose "no_safe_recovery". This is not a fallback for uncertainty; it is the correct, confident answer when nothing was actually observed to be changing.
4. Use "no_safe_recovery" at low confidence (below 0.3) only for the genuinely different situation of not being able to tell from the evidence given (e.g. the element's state was not captured at all).
5. Do NOT propose "dismiss_blocker" — there is no separate blocking element for this failure reason; naming one would be inventing evidence that was not provided.
6. Do NOT propose "force_not_allowed" (bypassing Playwright's own actionability check). If a real user can't interact with the element yet, forcing an interaction with it hides a genuine UI problem instead of describing it honestly. This option exists in the system but must never be the one you choose.

CRITICAL SELF-CONSISTENCY CHECK — perform this before writing your final answer: re-read your own "reasoning" against your chosen "strategy". If your reasoning does not point to an ACTUAL OBSERVED CHANGE in `disabled` between the two snapshots you were given, "wait_and_retry" is WRONG — choose "no_safe_recovery" instead.

EXAMPLE 1 — no change observed, nothing to wait for:
t0: disabled=true
t1 (+1200ms): disabled=true
Correct response: {"strategy": "no_safe_recovery", "confidence": 0.8, "reasoning": "The element was disabled at both observations 1200ms apart — nothing indicates it will become enabled on its own.", "suggested_wait_ms": null, "blocking_element": null}

EXAMPLE 2 — a real, observed change:
t0: disabled=true
t1 (+1200ms): disabled=false
Correct response: {"strategy": "wait_and_retry", "confidence": 0.85, "reasoning": "The element's disabled state actually changed from true to false between the two observations, confirming it is becoming actionable.", "suggested_wait_ms": 1200, "blocking_element": null}

You MUST respond with ONLY a JSON object, no other text before or after it, in exactly this shape:

{
  "strategy": "one of: wait_and_retry, no_safe_recovery",
  "confidence": 0.0 to 1.0,
  "reasoning": "one or two sentences naming the SPECIFIC observed difference (or lack of one) between t0 and t1 that led to this strategy",
  "suggested_wait_ms": "an integer number of milliseconds if strategy is wait_and_retry, otherwise null",
  "blocking_element": "always null for this failure reason — there is no separate blocking element"
}

Rules:
- confidence should reflect how certain you are this is the RIGHT recovery strategy, not just that the element is currently not enabled
- base your answer on the OBSERVED CHANGE (or absence of one) in `disabled` between t0 and t1
- never propose "dismiss_blocker" or "force_not_allowed" — see steps 5 and 6 above
- do not include explanation text outside the JSON object — your entire response must be parseable as JSON
- keep "reasoning" to one short sentence — brevity matters more than detail, a long reasoning field risks an incomplete response
"""


def build_user_prompt(context: HealingContext) -> str:
    """
    Renders a HealingContext into the user-facing prompt text. Reads
    from context.collector_metadata's temporal fields (target_state_t0/
    target_state_t1/target_state_changed_during_observation/
    observation_window_ms — ActionabilityCollector's ENABLED-specific
    fields), NOT context.dom_snapshot — same principle as
    visible_prompt.py's build_user_prompt().

    Sprint 8 scope: only ever called for ActionabilityReason.ENABLED —
    this function does not branch on reason itself, same as every other
    reason-specific build_user_prompt() in this project. That branching
    happens one layer up, in the provider (see ollama_provider.py).
    """
    metadata = context.collector_metadata or {}

    target_html = metadata.get("target_outer_html") or "<!-- not found -->"
    state_t0 = metadata.get("target_state_t0") or "<!-- not captured -->"
    state_t1 = metadata.get("target_state_t1") or "<!-- not captured -->"
    window_ms = metadata.get("observation_window_ms", "?")
    changed = metadata.get("target_state_changed_during_observation")

    return f"""A test action failed with this error:
{context.error_message}

The action being attempted was:
{context.original_code}

The page URL at the time of failure was:
{context.page_url}

The target element (selector is CORRECT, do not propose changing it — it exists in the DOM, is visible and stable, but is not enabled):
{target_html}

Target element observed state at t0 (immediately):
{state_t0}

Target element observed state at t1 (+{window_ms}ms):
{state_t1}

Did the disabled state actually change between t0 and t1? {changed}

Propose a recovery strategy as a JSON object, following the format and rules in your instructions."""