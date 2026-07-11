"""
failure_classifier.py

Resolves Gap #5 (LEARNINGS.md): "no failure classifier component" —
originally, and now resolves it a second time under a redesigned model
(see LEARNINGS.md "Sprint 6B (decision)").

HISTORY, for context on why two classification systems briefly coexist
in this file:

- Sprint 2: classify_playwright_error() + FailureType, SELECTOR_NOT_FOUND
  only fully classified.
- Sprint 4: fixed a real fill()/click() message-shape gap found live.
- Sprint 6A: added DETACHED_FROM_DOM classification (hand-crafted
  substrings, never verified against a live componentRemount.jsx run —
  the failure type itself was later deprioritized, see Gap #4).
- Sprint 6B (pre-coding diagnostics): six throwaway diagnostic tests
  plus real healing_decisions.log data established that Playwright's
  call log is genuinely two-stage — "did the locator resolve at all,"
  then, if so, one of five concrete actionability reasons — which the
  flat FailureType enum never captured. See LEARNINGS.md "Sprint 6B
  (pre-coding)" for the full evidence trail.
- Sprint 6B (decision): FailureCategory + ActionabilityReason +
  ClassifiedFailure adopted as the replacement model. See LEARNINGS.md
  "Sprint 6B (decision)" for the full reasoning, including why the first
  category is named LOCATOR_RESOLUTION rather than SELECTOR (Gap #12),
  and why REFERENCE stays in the model as a dormant category (Gap #4).

TRANSITIONAL STATE (this file, this change): parse_playwright_call_log()
is the new, live entry point — fully implemented and unit tested against
REAL captured Playwright output (not hand-crafted samples; see
tests/unit/test_failure_classifier.py for where each sample came from).
classify_playwright_error() + FailureType are LEFT IN PLACE, unchanged,
because base_provider.py's HealingContext and context_collector.py still
depend on them — removing them now would break currently-working code
before its replacement (the collector-layer vertical slice) exists. Per
LEARNINGS.md "Sprint 6B (decision)": no permanent FailureType
compatibility adapter is intended — this is a deliberate, temporary
coexistence for exactly one more vertical slice, not the final shape.
Marked DEPRECATED below; remove once ContextCollector/HealingContext
switch over.

KNOWN, DOCUMENTED LIMITS OF THIS PARSER (see docs/gaps.md for the full
entries — not repeated in full here to avoid the two copies drifting):
- Gap #13: every signal this parser depends on is Playwright's
  human-readable diagnostic text, not a documented, versioned API. A
  Playwright upgrade could silently change any of these strings.
  ClassifiedFailure.raw_message always retains the full original call
  log specifically so a parsing miss degrades to "unclassified, here is
  the raw text" rather than a silently wrong answer.
- Gap #14: FailureCategory.LOCATOR_RESOLUTION cannot distinguish WHY a
  locator never resolved (genuine selector drift vs. a conditionally-
  not-yet-mounted element vs. an unexpected app state) — Playwright's
  message is identical in all three cases.
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeout


# =============================================================================
# NEW MODEL (Sprint 6B decision) — live, this is what new code should use.
# =============================================================================

class FailureCategory(Enum):
    """
    The top-level split Playwright's own call log actually supports,
    confirmed empirically in Sprint 6B against real captured output —
    not a re-derivation of the old four-way FailureType split.
    """
    LOCATOR_RESOLUTION = "locator_resolution"  # locator did not resolve in time
    ACTIONABILITY = "actionability"            # locator resolved, an actionability check failed
    REFERENCE = "reference"                    # was actionable, then lost mid-action — dormant, see Gap #4
    UNKNOWN = "unknown"                        # classifier couldn't confidently determine a category


class ActionabilityReason(Enum):
    """
    Only meaningful when category == ACTIONABILITY. All five values
    confirmed against real, captured Playwright output in Sprint 6B
    (see tests/unit/test_failure_classifier.py for the exact captures).
    """
    VISIBLE = "visible"
    ENABLED = "enabled"
    EDITABLE = "editable"
    STABLE = "stable"
    RECEIVES_EVENTS = "receives_events"


@dataclass(frozen=True)
class ClassifiedFailure:
    """
    Return type of parse_playwright_call_log(). Frozen — a classification
    result is a fact about one specific error, not something a caller
    should mutate after the fact.

    actionability_reason is populated if and only if
    category == FailureCategory.ACTIONABILITY. blocking_element is
    populated if and only if actionability_reason == RECEIVES_EVENTS
    (the only reason Playwright's own log names a specific blocking
    element for).
    """
    category: FailureCategory
    action: Optional[str] = None                    # "click" / "fill" / "wait_for" / etc., parsed from the message
    locator_resolved: Optional[bool] = None
    actionability_reason: Optional[ActionabilityReason] = None
    blocking_element: Optional[str] = None
    raw_message: str = ""                            # ALWAYS populated — see Gap #13


# Reference (dormant) substrings — carried over unchanged from Sprint 6A.
# Checked FIRST, before the locator-resolution logic below, for the same
# ordering reason Sprint 6A originally established: a detached-mid-action
# message also contains "waiting for locator" and (usually) "locator
# resolved to", so the more specific reference signal must win before
# either of the other two branches gets a chance to misclassify it.
_REFERENCE_SUBSTRINGS = (
    "not attached to the dom",
    "element is not attached",
    "was detached from the dom",
)

# One substring per ActionabilityReason, each confirmed verbatim against
# real captured Playwright output in Sprint 6B — not inferred from
# documentation. See tests/unit/test_failure_classifier.py for the exact
# raw messages these were taken from.
_ACTIONABILITY_REASON_SUBSTRINGS = {
    ActionabilityReason.ENABLED: "element is not enabled",
    ActionabilityReason.VISIBLE: "element is not visible",
    ActionabilityReason.EDITABLE: "element is not editable",
    ActionabilityReason.STABLE: "element is not stable",
}

# receives_events is checked separately, not folded into the dict above,
# because unlike the other four it's a substring Playwright appends
# AFTER naming the specific blocking element on the same line
# (e.g. '<div id="overlay">...</div> intercepts pointer events') — see
# _extract_blocking_element() below.
_RECEIVES_EVENTS_MARKER = "intercepts pointer events"

_LOCATOR_RESOLVED_MARKER = "locator resolved to"

_ACTION_RE = re.compile(r"^Locator\.(\w+):")


def _extract_action(raw_message: str) -> Optional[str]:
    """
    Playwright's own messages start with "Locator.<action>: Timeout...".
    Extracts the action name so callers don't have to pass it in
    separately when it's already right there in the exception.
    """
    match = _ACTION_RE.match(raw_message.strip())
    return match.group(1) if match else None


def _extract_blocking_element(raw_message: str) -> Optional[str]:
    """
    Finds the line containing the receives_events marker and returns
    whatever precedes it on that line — Playwright's own call log names
    the specific blocking element right there, e.g.:
        - <div id="overlay">...</div> intercepts pointer events
    Confirmed against real captured output in Sprint 6B; this is the
    richest of the five actionability reasons for exactly this reason —
    it names the culprit, not just the condition.
    """
    for line in raw_message.splitlines():
        stripped = line.strip()
        if _RECEIVES_EVENTS_MARKER in stripped:
            prefix = stripped.split(_RECEIVES_EVENTS_MARKER)[0].strip()
            if prefix.startswith("-"):
                prefix = prefix[1:].strip()
            return prefix or None
    return None


def parse_playwright_call_log(error: Exception) -> ClassifiedFailure:
    """
    Single entry point for the new model. Given the exception Playwright
    raised, returns a ClassifiedFailure describing what actually
    happened, based on the STRUCTURE of the call log — not a flat
    substring check on the whole message (see module docstring: this is
    a genuine rewrite, not a patched classify_playwright_error()).

    Algorithm, confirmed against real Playwright output in Sprint 6B
    (see tests/unit/test_failure_classifier.py):

    1. Not a Playwright TimeoutError at all -> UNKNOWN. Out of scope,
       same as the old classifier — network errors, app exceptions
       surfaced through the page, etc.
    2. Reference substrings present (dormant category, Gap #4) -> REFERENCE.
    3. No "locator resolved to" anywhere in the message -> LOCATOR_RESOLUTION.
       Playwright never got past resolving the locator. WHY it never
       resolved (selector drift, conditional mount, wrong app state) is
       NOT determinable from the message alone — see Gap #14.
    4. "locator resolved to" IS present -> ACTIONABILITY. The locator
       found a real element; the action itself could not proceed. Which
       of the five reasons is determined by matching the specific
       "element is not X" substring, or the receives_events marker
       (checked first, since real captures show it appears alongside
       "element is visible, enabled and stable" — the other substrings
       would falsely NOT match here anyway, but checking receives_events
       explicitly first keeps the intent obvious rather than relying on
       that coincidence).
    5. Locator resolved but no recognized reason substring matched ->
       UNKNOWN, with locator_resolved=True preserved. Better to say
       "don't know" than to guess at a sixth condition this parser
       doesn't yet handle.
    """
    raw_message = str(error)

    if not isinstance(error, PlaywrightTimeout):
        return ClassifiedFailure(category=FailureCategory.UNKNOWN, raw_message=raw_message)

    message = raw_message.lower()
    action = _extract_action(raw_message)

    if any(substr in message for substr in _REFERENCE_SUBSTRINGS):
        return ClassifiedFailure(category=FailureCategory.REFERENCE, action=action, raw_message=raw_message)

    locator_resolved = _LOCATOR_RESOLVED_MARKER in message

    if not locator_resolved:
        if "waiting for locator" in message:
            return ClassifiedFailure(
                category=FailureCategory.LOCATOR_RESOLUTION,
                action=action,
                locator_resolved=False,
                raw_message=raw_message,
            )
        return ClassifiedFailure(category=FailureCategory.UNKNOWN, action=action, raw_message=raw_message)

    if _RECEIVES_EVENTS_MARKER in message:
        return ClassifiedFailure(
            category=FailureCategory.ACTIONABILITY,
            action=action,
            locator_resolved=True,
            actionability_reason=ActionabilityReason.RECEIVES_EVENTS,
            blocking_element=_extract_blocking_element(raw_message),
            raw_message=raw_message,
        )

    for reason, substr in _ACTIONABILITY_REASON_SUBSTRINGS.items():
        if substr in message:
            return ClassifiedFailure(
                category=FailureCategory.ACTIONABILITY,
                action=action,
                locator_resolved=True,
                actionability_reason=reason,
                raw_message=raw_message,
            )

    return ClassifiedFailure(
        category=FailureCategory.UNKNOWN,
        action=action,
        locator_resolved=True,
        raw_message=raw_message,
    )


# =============================================================================
# OLD MODEL (Sprint 2-6A) — DEPRECATED, kept only until ContextCollector and
# HealingContext switch over to the new model above. Do not add new code
# against FailureType or classify_playwright_error(); use
# parse_playwright_call_log() / FailureCategory / ActionabilityReason instead.
# =============================================================================

class FailureType(Enum):
    """
    DEPRECATED — see module docstring. Kept only so base_provider.py's
    HealingContext and context_collector.py keep working until the next
    vertical slice replaces them.
    """
    SELECTOR_NOT_FOUND = "selector_not_found"
    DETACHED_FROM_DOM = "detached_from_dom"
    NOT_VISIBLE = "not_visible"
    TIMEOUT_WAITING = "timeout_waiting"
    UNKNOWN = "unknown"


_DETACHED_SUBSTRINGS = _REFERENCE_SUBSTRINGS  # same strings, old name


def classify_playwright_error(error: Exception, page=None, selector: str = None) -> FailureType:
    """
    DEPRECATED — see module docstring. Behavior unchanged from Sprint 6A;
    not touched by the Sprint 6B model change. Superseded by
    parse_playwright_call_log() above.
    """
    if not isinstance(error, PlaywrightTimeout):
        return FailureType.UNKNOWN

    message = str(error).lower()

    if any(substr in message for substr in _DETACHED_SUBSTRINGS):
        return FailureType.DETACHED_FROM_DOM

    if "waiting for locator" in message:
        return FailureType.SELECTOR_NOT_FOUND

    return FailureType.UNKNOWN