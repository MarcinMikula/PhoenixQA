"""
visible_prompt.py

Builds the system + user prompt for FailureCategory.ACTIONABILITY /
ActionabilityReason.VISIBLE — a locator that resolved fine (the element
exists in the DOM), but Playwright's own actionability check reports it
as not visible (visibility:hidden, display:none, or a zero-size
bounding box on the element or an ancestor).

CATEGORICALLY SIMPLER than RECEIVES_EVENTS, deliberately: there is no
separate "blocker" element here. Playwright's own message for this
reason — confirmed against the real captured call log in
tests/unit/test_failure_classifier.py — is just "element is not
visible," naming nothing else. The model only ever has ONE element's
evidence to reason about: the target's own observed state.

EVIDENCE IS TEMPORAL, NOT DECLARATIVE — a deliberate design correction
made during this slice, per direct discussion, before RECEIVES_EVENTS'
approach (checking whether a CSS animation/transition is DECLARED) was
copied here unchanged. A raised, valid concern: a declared
`animation-iteration-count: infinite` or a `transition-property:
opacity` only says a change is CAPABLE of happening, not that one is
ACTUALLY in progress or will resolve anything. This prompt instead
tells the model whether the element's state was OBSERVED to change
across two real snapshots (see
phoenix/collector/collectors/actionability_collector.py) — an empirical
fact, not a style declaration. See that module's docstring and
actionability_policy.py's validate_visible_strategy() for the full
reasoning and why RECEIVES_EVENTS was deliberately NOT retrofitted with
this stronger standard in the same commit.

NAMING NOTE, same transitional pattern already established for
prompt_templates.py vs. the prompts/ package: this module is named
after its REASON (visible_prompt.py), while its sibling
actionability_prompt.py is implicitly RECEIVES_EVENTS-specific despite
its generic name — renaming that file is deferred cleanup, not bundled
into this commit, same reasoning as before (a working file shouldn't
move as a side effect of an unrelated feature commit).

SELF-CONSISTENCY INSTRUCTION carried over directly from
actionability_prompt.py's revision (Sprint 6B): that revision fixed the
model's DIAGNOSIS on RECEIVES_EVENTS but not its DECISION — llama3.2
correctly named a blocker "persistent" and still proposed
wait_and_retry anyway, deterministically, which is why
actionability_policy.py exists as a second line of defense. The same
self-consistency instruction is included here from the start, on the
chance it fares better on this simpler, single-element evidence shape —
but per that same investigation, PhoenixQA does not rely on the prompt
alone; see actionability_policy.py's validate_visible_strategy(), which
is the actual, deterministic gate regardless of what this prompt
achieves.
"""
from phoenix.ai.base_provider import HealingContext

SYSTEM_PROMPT = """You are a test automation engineer's assistant. A Playwright test failed while trying to interact with an element that WAS found on the page (the selector is correct and does not need to change) — but Playwright reports the element as NOT VISIBLE. This is a test environment that intentionally hides elements (behind loading states, collapsed sections, delayed reveals) to simulate real-world timing and layout issues.

IMPORTANT: unlike a "selector not found" problem, there is nothing to rename here. The target element's selector is correct and must NOT be changed. Your job is to decide, from the element's own observed state, what recovery strategy makes sense — not to propose a new selector.

Unlike some other actionability problems, there is no separate "blocking element" here — Playwright is not telling you something else is in the way. The element itself is what is not visible right now (common real causes: visibility:hidden, display:none, zero width/height, or the same on a parent element).

You will be given the element's state observed TWICE — once immediately, and once again after a short real wait — rather than just its CSS declarations. This matters: a CSS transition or animation being DECLARED on an element does not mean a change is actually happening or will resolve anything (an infinitely-repeating animation, for example, never resolves). Whether the element's actual state (visible/hidden, size, opacity) CHANGED between the two observations is the evidence that matters here, not what its style sheet merely permits.

HOW TO DECIDE — follow these steps in order:
1. Compare the element's observed state at the first check (t0) against the second check (t1, after the wait).
2. If the state ACTUALLY CHANGED between t0 and t1 (visibility flipped, display changed, opacity changed, or its size changed) — that is real evidence something is in progress. Propose "wait_and_retry" with a suggested_wait_ms roughly matching how long you were told the observation window was.
3. If the state did NOT change between t0 and t1, propose "no_safe_recovery". This is not a fallback for uncertainty; it is the correct, confident answer when nothing was actually observed to be changing, regardless of what any CSS animation/transition property might declare is theoretically possible.
4. Use "no_safe_recovery" at low confidence (below 0.3) only for the genuinely different situation of not being able to tell from the evidence given (e.g. the element's state was not captured at all).
5. Do NOT propose "dismiss_blocker" — there is no separate blocking element for this failure reason; naming one would be inventing evidence that was not provided.
6. Do NOT propose "force_not_allowed" (bypassing Playwright's own actionability check). If a real user can't see the element, forcing an interaction with it hides a genuine UI problem instead of describing it honestly. This option exists in the system but must never be the one you choose.

CRITICAL SELF-CONSISTENCY CHECK — perform this before writing your final answer: re-read your own "reasoning" against your chosen "strategy". If your reasoning does not point to an ACTUAL OBSERVED CHANGE between the two snapshots you were given (not a CSS property that merely could permit a change), "wait_and_retry" is WRONG — choose "no_safe_recovery" instead.

EXAMPLE 1 — no change observed, nothing to wait for:
t0: visibility=hidden, display=block, opacity=1, bounding box 200x30
t1 (+1200ms): visibility=hidden, display=block, opacity=1, bounding box 200x30
Correct response: {"strategy": "no_safe_recovery", "confidence": 0.8, "reasoning": "The element's state was identical at both observations 1200ms apart — nothing indicates it will become visible on its own.", "suggested_wait_ms": null, "blocking_element": null}

EXAMPLE 2 — a real, observed change:
t0: visibility=hidden, display=block, opacity=1, bounding box 200x30
t1 (+1200ms): visibility=visible, display=block, opacity=1, bounding box 200x30
Correct response: {"strategy": "wait_and_retry", "confidence": 0.85, "reasoning": "The element's visibility actually changed from hidden to visible between the two observations, confirming it is becoming actionable.", "suggested_wait_ms": 1200, "blocking_element": null}

You MUST respond with ONLY a JSON object, no other text before or after it, in exactly this shape:

{
  "strategy": "one of: wait_and_retry, no_safe_recovery",
  "confidence": 0.0 to 1.0,
  "reasoning": "one or two sentences naming the SPECIFIC observed difference (or lack of one) between t0 and t1 that led to this strategy",
  "suggested_wait_ms": "an integer number of milliseconds if strategy is wait_and_retry, otherwise null",
  "blocking_element": "always null for this failure reason — there is no separate blocking element"
}

Rules:
- confidence should reflect how certain you are this is the RIGHT recovery strategy, not just that the element is currently not visible
- base your answer on the OBSERVED CHANGE (or absence of one) between t0 and t1, never on a CSS animation/transition property alone — a declared capability is not the same as an observed change
- never propose "dismiss_blocker" or "force_not_allowed" — see steps 5 and 6 above
- do not include explanation text outside the JSON object — your entire response must be parseable as JSON
- keep "reasoning" to one short sentence — brevity matters more than detail, a long reasoning field risks an incomplete response
"""


def build_user_prompt(context: HealingContext) -> str:
    """
    Renders a HealingContext into the user-facing prompt text. Reads
    from context.collector_metadata's temporal fields (target_state_t0/
    target_state_t1/target_state_changed_during_observation/
    observation_window_ms — ActionabilityCollector's VISIBLE-specific
    fields), NOT context.dom_snapshot — same principle as
    actionability_prompt.py's build_user_prompt(): dom_snapshot is a
    short human-readable summary for a log reader, not the shape this
    prompt is built to consume.

    Sprint 6B scope: only ever called for ActionabilityReason.VISIBLE —
    this function does not branch on reason itself, same as every other
    reason-specific build_user_prompt() in this project. That branching
    happens one layer up, in the provider (see ollama_provider.py).
    """
    metadata = context.collector_metadata or {}

    target_html = metadata.get("target_outer_html") or "<!-- not found -->"
    target_box = metadata.get("target_bounding_box")
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

The target element (selector is CORRECT, do not propose changing it — it exists in the DOM but is not visible):
{target_html}

Target element bounding box (at t0): {target_box}

Target element observed state at t0 (immediately):
{state_t0}

Target element observed state at t1 (+{window_ms}ms):
{state_t1}

Did the state actually change between t0 and t1? {changed}

Propose a recovery strategy as a JSON object, following the format and rules in your instructions."""
