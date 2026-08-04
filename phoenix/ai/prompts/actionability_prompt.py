"""
actionability_prompt.py

Builds the system + user prompt for FailureCategory.ACTIONABILITY /
ActionabilityReason.RECEIVES_EVENTS — a locator that resolved fine, but
whose element could not receive the pointer event because something
else (an overlay, a modal, a sticky header) is sitting on top of it.
This is a categorically different task from the selector-replacement
prompt in phoenix/ai/prompt_templates.py: there the model looks for a
NEW matching attribute value; here the target element is already
correct and unchanged — the model has to look at TWO elements (the
target and whatever's blocking it) and decide what to do about the
blocker.

Transitional module location, per direct discussion: phoenix/ai/prompts/
is meant to eventually hold one module per category
(prompts/selector_prompt.py, prompts/actionability_prompt.py), but this
commit only introduces the package for the new actionability path.
prompt_templates.py stays where it is for now — migrating it is a
separate, later cleanup, not bundled into the commit whose actual goal
is the ActionabilityStrategy provider path. See LEARNINGS.md "Sprint 6B
(implementation) — actionability provider path" for the full reasoning.

Sprint 6B scope: only ActionabilityReason.RECEIVES_EVENTS — same
one-reason-at-a-time discipline every other Sprint 6 slice has used.
VISIBLE/ENABLED/EDITABLE/STABLE all need their own prompt eventually
("propose a wait strategy" is a different task from "propose which
overlay to dismiss"), not this one reused across all five reasons.
"""
from phoenix.ai.base_provider import HealingContext

SYSTEM_PROMPT = """You are a test automation engineer's assistant. A Playwright test failed while trying to interact with an element that WAS found on the page (the selector is correct and does not need to change) — but the click or fill could not go through because something else is currently on top of it, intercepting the pointer event. This is a test environment that intentionally overlays elements (banners, modals, loading overlays) to simulate real-world UI interference.

IMPORTANT: unlike a "selector not found" problem, there is nothing to rename here. The target element's selector is correct and must NOT be changed. Your job is to look at what is blocking it and recommend a RECOVERY STRATEGY, not a new selector.

You will be given two independently-gathered pieces of evidence about the blocker:
1. The element Playwright's own error log named as intercepting the pointer event.
2. An element found independently by probing the exact center point of the target element in the browser (this may be missing if the blocker had already disappeared by the time the probe ran, or may confirm the same element as source 1).
These two sources may agree, partially agree, or disagree. Read both before deciding — do not assume the second one exists.

HOW TO DECIDE — follow these steps in order:
1. Look at the blocking element's HTML, computed style (position, z-index, pointer-events, opacity, display, visibility), and bounding box.
2. Decide whether the blocker looks TRANSIENT — a loading spinner, a fade-in banner, something whose style suggests it is actively animating or about to disappear on its own (e.g. an opacity/transform transition, a known "toast" or "spinner" pattern). If so, propose "wait_and_retry" with a short suggested_wait_ms (typically 300-2000).
3. If the blocker is NOT transient (it looks persistent — plain, static styling, full-viewport, no animation indicators), look SPECIFICALLY inside the blocker's own HTML for an actual DISMISS AFFORDANCE: a button, link, or other interactive element whose text or attributes suggest closing/accepting/dismissing (e.g. "Accept", "Close", "×", "Got it", a <button> or <a> tag). Only propose "dismiss_blocker" if you can point to a SPECIFIC interactive element for this purpose — put THAT element's HTML (not the whole blocker container) in "blocking_element".
4. If the blocker is persistent AND you found no dismiss affordance anywhere in its HTML, propose "no_safe_recovery". This is not merely a fallback for uncertainty — it is the CORRECT, confident answer when a blocker is clearly there to stay and there is nothing in the page for a real user (or a script) to interact with to remove it. A plain, empty, full-viewport <div> with no text or controls is exactly this case.
5. Use "no_safe_recovery" at low confidence (below 0.3) only for the genuinely different situation of not being able to tell what the blocker even is from the evidence given.
6. Do NOT propose "force_not_allowed" (bypassing Playwright's own actionability check). A real user's mouse click would be blocked by the same overlay a force-click ignores — proposing a bypass would hide a genuine UI problem instead of describing it honestly. This option exists in the system but must never be the one you choose.

CRITICAL SELF-CONSISTENCY CHECK — perform this before writing your final answer: re-read your own "reasoning" against your chosen "strategy". If your reasoning states or implies the blocker is persistent, not transient, or will not go away on its own, "wait_and_retry" is WRONG regardless of how the rest of your reasoning sounds — waiting only makes sense if you believe the blocker will actually disappear. Choose "dismiss_blocker" (only with a specific affordance identified) or "no_safe_recovery" instead.

EXAMPLE 1 — persistent blocker WITH a dismiss affordance:
Blocking element HTML: <div class="cookie-consent-banner"><p>We use cookies to improve your experience.</p><button data-testid="cookie-accept">Accept</button></div>
Computed style: position: fixed, zIndex: 2000, pointerEvents: auto, opacity: 1, display: block, visibility: visible
Correct response: {"strategy": "dismiss_blocker", "confidence": 0.85, "reasoning": "A cookie-consent banner is blocking the target; it is persistent (no animation indicators) but has a visible Accept button to dismiss it.", "suggested_wait_ms": null, "blocking_element": "<button data-testid=\\"cookie-accept\\">Accept</button>"}

EXAMPLE 2 — persistent blocker with NO dismiss affordance (real captured case from this project's own Chaos App):
Blocking element HTML: <div data-testid="chaos-pointer-events-overlay" style="position: fixed; top: 0px; left: 0px; width: 100vw; height: 100vh; background: transparent; z-index: 9999;"></div>
Computed style: position: fixed, zIndex: 9999, pointerEvents: auto, opacity: 1, display: block, visibility: visible
Correct response: {"strategy": "no_safe_recovery", "confidence": 0.75, "reasoning": "The overlay is a full-viewport fixed div with no text, buttons, or links anywhere in its HTML and no styling suggesting it will disappear — there is nothing to wait for and nothing to dismiss.", "suggested_wait_ms": null, "blocking_element": null}

You MUST respond with ONLY a JSON object, no other text before or after it, in exactly this shape:

{
  "strategy": "one of: wait_and_retry, dismiss_blocker, no_safe_recovery",
  "confidence": 0.0 to 1.0,
  "reasoning": "one or two sentences naming the SPECIFIC evidence (element, style, or its absence) that led to this strategy",
  "suggested_wait_ms": "an integer number of milliseconds if strategy is wait_and_retry, otherwise null",
  "blocking_element": "the SPECIFIC dismiss-affordance element's HTML if strategy is dismiss_blocker, otherwise null"
}

Rules:
- confidence should reflect how certain you are this is the RIGHT recovery strategy, not just that something is blocking the target
- never propose "force_not_allowed" — see step 6 above
- if the two blocker sources disagree, say so in "reasoning" rather than silently picking one
- do not include explanation text outside the JSON object — your entire response must be parseable as JSON
- keep "reasoning" to one short sentence — brevity matters more than detail, a long reasoning field risks an incomplete response
"""


def build_user_prompt(context: HealingContext) -> str:
    """
    Renders a HealingContext into the user-facing prompt text. Reads
    from context.collector_metadata (ActionabilityCollector's richer,
    structured data), NOT context.dom_snapshot — dom_snapshot is a
    short human-readable summary meant for a human reading a log, not
    the shape this prompt is built to consume. See
    phoenix/collector/collectors/actionability_collector.py for exactly
    which keys collector_metadata carries.

    Sprint 6B scope: only ever called for ActionabilityReason.RECEIVES_EVENTS
    — this function does not branch on reason itself, same as
    prompt_templates.build_user_prompt() never branches on category.
    That branching happens one layer up, in the provider (see
    ollama_provider.py).
    """
    metadata = context.collector_metadata or {}

    target_html = metadata.get("target_outer_html") or "<!-- not found -->"
    target_box = metadata.get("target_bounding_box")

    blocker_from_call_log = metadata.get("blocking_element_from_call_log") or "<!-- not named in call log -->"
    blocker_html = metadata.get("blocking_element_outer_html")
    blocker_box = metadata.get("blocking_element_bounding_box")
    blocker_style = metadata.get("blocking_element_computed_style")

    if blocker_html:
        blocker_section = f"""Blocking element HTML (independently confirmed via a DOM probe at the target's center point):
{blocker_html}

Blocking element bounding box: {blocker_box}
Blocking element computed style: {blocker_style}"""
    else:
        blocker_section = (
            "No independent DOM-probe confirmation was found — the blocker named "
            "in the call log below may have already disappeared, or the target's "
            "own center point is no longer covered. Reason about the call log "
            "evidence alone."
        )

    return f"""A test action failed with this error:
{context.error_message}

The action being attempted was:
{context.original_code}

The page URL at the time of failure was:
{context.page_url}

The target element (selector is CORRECT, do not propose changing it):
{target_html}

Target element bounding box: {target_box}

Blocking element named by Playwright's own error log:
{blocker_from_call_log}

{blocker_section}

Propose a recovery strategy as a JSON object, following the format and rules in your instructions."""