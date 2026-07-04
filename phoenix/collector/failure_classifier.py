"""
failure_classifier.py

Resolves Gap #5 (LEARNINGS.md): "no failure classifier component."
Before this file existed, FailureType was declared but nothing actually
produced one from a real Playwright exception — classify_playwright_error()
was referenced in pseudo-code but never designed.

SPRINT 2 SCOPE: only SELECTOR_NOT_FOUND was fully classified and routed
downstream. DETACHED_FROM_DOM / NOT_VISIBLE / TIMEOUT_WAITING were defined
here (so the enum didn't need reshaping later) but Context Collector
raised NotImplementedError for them — see LEARNINGS.md "Gap #4" for why
this sequencing was a deliberate choice, not an oversight.

SPRINT 6A SCOPE (this change): DETACHED_FROM_DOM gets a real classification
branch — CLASSIFIER ONLY, per the Sprint 6A exit criterion in LEARNINGS.md
("Sprint 6 (pre-coding)"). Context Collector still raises NotImplementedError
for DETACHED_FROM_DOM; that's Sprint 6B's job. This file's only
responsibility this sub-sprint is: given a real Playwright error produced
by chaos_app's componentRemount.jsx (TIMEOUT trigger, see LEARNINGS.md
"Sprint 6"), correctly return FailureType.DETACHED_FROM_DOM instead of
UNKNOWN or a false-positive SELECTOR_NOT_FOUND.

IMPORTANT EPISTEMIC NOTE (read before trusting this blindly): the
SELECTOR_NOT_FOUND branch below was corrected TWICE after real end-to-end
runs revealed message shapes that hand-crafted unit test samples didn't
anticipate (see LEARNINGS.md Sprint 4 — the fill() vs click() "to be
visible" gap). The DETACHED_FROM_DOM branch added in Sprint 6A has NOT
yet been through that same live-run correction cycle — the message
substrings below are inferred from Playwright's public documentation of
its own actionability-check wording, not yet confirmed against a real
`pytest tests/chaos/ -m chaos -s` run against componentRemount.jsx. Treat
this branch as "best guess, pending live verification" until LEARNINGS.md
has a Sprint 6A "Verified live" entry saying otherwise — same posture the
project took with every prior classifier change.
"""
from enum import Enum

from playwright.sync_api import TimeoutError as PlaywrightTimeout


class FailureType(Enum):
    """
    Categorizes WHY a Playwright action failed — not just THAT it failed.
    Each value needs different collected context and a different LLM
    prompt strategy (Sprint 3/6): "propose a new selector" is a different
    task than "propose a wait/retry strategy."
    """
    SELECTOR_NOT_FOUND = "selector_not_found"   # element never existed with this selector
    DETACHED_FROM_DOM = "detached_from_dom"      # existed, framework removed it mid-action
    NOT_VISIBLE = "not_visible"                  # exists in DOM, but not visible (spinner/overlay)
    TIMEOUT_WAITING = "timeout_waiting"           # never reached an actionable state
    UNKNOWN = "unknown"                           # classifier couldn't determine a type


# Substrings Playwright's own actionability-check logging uses when an
# action's target element was detached from the DOM mid-action — as
# opposed to never having existed at all (SELECTOR_NOT_FOUND). Checked
# BEFORE the generic "waiting for locator" substring below, because a
# detached-mid-action failure's message ALSO contains "waiting for
# locator" (Playwright logs that for every action) — the "not attached"
# phrase is the more specific signal and must win when both are present.
#
# Sprint 6A note: these substrings are Playwright's documented
# actionability-check vocabulary, not yet confirmed against a captured
# real error message from a live componentRemount.jsx run. If a live run
# produces a message shape not covered here, that is expected to surface
# the same way Sprint 4's fill()/click() gap did — fix here, add a
# regression test, log it in LEARNINGS.md. Not a design flaw to avoid,
# just the next expected step in this project's established pattern.
_DETACHED_SUBSTRINGS = (
    "not attached to the dom",
    "element is not attached",
    "was detached from the dom",
)


def classify_playwright_error(error: Exception, page=None, selector: str = None) -> FailureType:
    """
    Single entry point Context Collector routes on. Given the exception
    Playwright raised (and optionally a live page + the selector that
    failed), returns which FailureType this is.

    Sprint 2: only distinguishes SELECTOR_NOT_FOUND reliably — this is
    the failure mode our Chaos App mechanisms (selector_rotation,
    dom_mutation) actually produce, and the one the rest of Sprint 2-5
    is built around end-to-end.

    Sprint 6A: adds DETACHED_FROM_DOM classification, using message
    substrings rather than a DOM probe — see module docstring for why
    this is flagged as pending live verification, same epistemic caution
    every prior classifier change in this file has needed.

    Sprint 6/future TODO: NOT_VISIBLE classification needs more than the
    exception alone — likely requires probing the page at failure time
    (e.g. "does an element matching this selector exist, but with
    visibility:hidden or zero size?"). That probe doesn't exist yet, so
    this function can't safely return that value today even though the
    enum already has room for it.
    """
    if not isinstance(error, PlaywrightTimeout):
        # Sprint 2 only knows how to reason about Playwright's own
        # timeout-style failures. Anything else (network errors, app
        # exceptions surfaced through the page, etc.) is out of scope
        # for now — explicitly UNKNOWN rather than silently guessing.
        return FailureType.UNKNOWN

    message = str(error).lower()

    # Checked FIRST, before the generic "waiting for locator" check
    # below — see _DETACHED_SUBSTRINGS docstring for why this ordering
    # matters. A message containing one of these phrases means the
    # element existed and was found at some point during the action,
    # then disappeared mid-action — categorically different from
    # SELECTOR_NOT_FOUND, where nothing ever matched at all.
    if any(substr in message for substr in _DETACHED_SUBSTRINGS):
        return FailureType.DETACHED_FROM_DOM

    # Playwright's timeout message differs depending on WHY waiting for
    # the locator failed, AND depending on which action was being
    # performed. Discovered via a real end-to-end run (see LEARNINGS.md):
    # click()-style actions log "waiting for locator(...) to be visible",
    # but fill()-style actions only log "waiting for locator(...)" with
    # no "to be visible" suffix — fill() waits for editability, not
    # strictly visibility, so its log wording is narrower. The original
    # check required "to be visible" unconditionally and silently
    # misclassified every fill() timeout as UNKNOWN.
    if "waiting for locator" in message:
        # Playwright found zero matching elements for the full timeout
        # window — this is our case: rotated/mutated selector, nothing
        # in the DOM ever matched it. True for both click() and fill()
        # shaped messages.
        return FailureType.SELECTOR_NOT_FOUND

    # Anything else Playwright-timeout-shaped that we can't confidently
    # bucket yet. Better to say UNKNOWN than to mislabel it as
    # SELECTOR_NOT_FOUND and send the wrong kind of context downstream.
    return FailureType.UNKNOWN