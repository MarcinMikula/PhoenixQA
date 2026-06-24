"""
failure_classifier.py

Resolves Gap #5 (LEARNINGS.md): "no failure classifier component."
Before this file existed, FailureType was declared but nothing actually
produced one from a real Playwright exception — classify_playwright_error()
was referenced in pseudo-code but never designed.

SPRINT 2 SCOPE: only SELECTOR_NOT_FOUND is fully classified and routed
downstream. DETACHED_FROM_DOM / NOT_VISIBLE / TIMEOUT_WAITING are defined
here (so the enum doesn't need reshaping later) but Context Collector
raises NotImplementedError for them until Sprint 6 — see LEARNINGS.md
"Gap #4" for why this sequencing was a deliberate choice, not an oversight.
"""
from enum import Enum

from playwright.sync_api import TimeoutError as PlaywrightTimeout


class FailureType(Enum):
    """
    Categorizes WHY a Playwright action failed — not just THAT it failed.
    Each value needs different collected context and a different LLM
    prompt strategy (Sprint 3): "propose a new selector" is a different
    task than "propose a wait/retry strategy."
    """
    SELECTOR_NOT_FOUND = "selector_not_found"   # element never existed with this selector
    DETACHED_FROM_DOM = "detached_from_dom"      # existed, framework removed it mid-action
    NOT_VISIBLE = "not_visible"                  # exists in DOM, but not visible (spinner/overlay)
    TIMEOUT_WAITING = "timeout_waiting"           # never reached an actionable state
    UNKNOWN = "unknown"                           # classifier couldn't determine a type


def classify_playwright_error(error: Exception, page=None, selector: str = None) -> FailureType:
    """
    Single entry point Context Collector routes on. Given the exception
    Playwright raised (and optionally a live page + the selector that
    failed), returns which FailureType this is.

    Sprint 2: only distinguishes SELECTOR_NOT_FOUND reliably — this is
    the failure mode our Chaos App mechanisms (selector_rotation,
    dom_mutation) actually produce, and the one the rest of Sprint 2-5
    is built around end-to-end.

    Sprint 6 TODO: DETACHED_FROM_DOM and NOT_VISIBLE classification
    needs more than the exception alone — likely requires probing the
    page at failure time (e.g. "does this exact node still exist
    anywhere in the DOM, just detached from its old parent?" vs
    "does an element matching this selector exist, but with
    visibility:hidden or zero size?"). That probe doesn't exist yet,
    so this function can't safely return those values today even
    though the enum already has room for them.
    """
    if not isinstance(error, PlaywrightTimeout):
        # Sprint 2 only knows how to reason about Playwright's own
        # timeout-style failures. Anything else (network errors, app
        # exceptions surfaced through the page, etc.) is out of scope
        # for now — explicitly UNKNOWN rather than silently guessing.
        return FailureType.UNKNOWN

    message = str(error).lower()

    # Playwright's timeout message differs depending on WHY waiting for
    # the locator failed. These substring checks are intentionally
    # narrow for Sprint 2 — broadening them is exactly the Sprint 6 work,
    # once DETACHED_FROM_DOM / NOT_VISIBLE have a real Chaos App
    # mechanism to validate against (see LEARNINGS.md).
    if "waiting for locator" in message and "to be visible" in message:
        # Playwright found zero matching elements for the full timeout
        # window — this is our case: rotated/mutated selector, nothing
        # in the DOM ever matched it.
        return FailureType.SELECTOR_NOT_FOUND

    # Anything else Playwright-timeout-shaped that we can't confidently
    # bucket yet. Better to say UNKNOWN than to mislabel it as
    # SELECTOR_NOT_FOUND and send the wrong kind of context downstream.
    return FailureType.UNKNOWN
