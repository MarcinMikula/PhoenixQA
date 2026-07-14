"""
test_failure_classifier.py

Unit tests for parse_playwright_call_log() / FailureCategory /
ActionabilityReason / ClassifiedFailure (Sprint 6B decision).

DELIBERATELY DIFFERENT from every prior classifier test file in this
project's history: every message below is a VERBATIM real Playwright
capture from the Sprint 6B diagnostic sessions (six throwaway diagnostic
tests, plus two real entries pulled directly from healing_decisions.log)
— not a hand-crafted guess at what Playwright "probably" outputs. This
project has been burned twice by hand-crafted samples that turned out
wrong once checked against real output (Sprint 4's fill()/click() gap,
Sprint 6B's own discovery that Sprint 2's original click() sample never
matched real output either) — this file exists specifically to not
repeat that pattern a third time.

The old classify_playwright_error()/FailureType model this file replaces
has been fully removed from failure_classifier.py (see LEARNINGS.md
"Sprint 6B (implementation)") — there is no old-model test file to point
to anymore; this file is the only classifier test suite now.
"""
import pytest

from phoenix.collector.failure_classifier import (
    ActionabilityReason,
    FailureCategory,
    parse_playwright_call_log,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeout


@pytest.mark.unit
class TestNonPlaywrightAndUnrecognizedShapes:
    def test_non_playwright_exception_is_unknown(self):
        result = parse_playwright_call_log(ValueError("not a playwright error"))
        assert result.category == FailureCategory.UNKNOWN
        assert result.locator_resolved is None

    def test_unrecognized_timeout_shape_is_unknown_not_misclassified(self):
        error = PlaywrightTimeout("Timeout 10000ms exceeded. some other reason entirely")
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.UNKNOWN


@pytest.mark.unit
class TestLocatorResolution:
    """
    Both messages below are VERBATIM captures pulled directly from real
    entries in healing_decisions.log (selector_rotation active, real
    Chaos App runs) — not reconstructed from memory. Confirms the
    "locator never resolved" shape is identical for click() and fill(),
    with no reason suffix of any kind.
    """

    def test_real_click_selector_not_found_from_production_log(self):
        error = PlaywrightTimeout(
            "Locator.click: Timeout 10000ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='btn-login']\")\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.LOCATOR_RESOLUTION
        assert result.locator_resolved is False
        assert result.action == "click"

    def test_real_fill_selector_not_found_from_production_log(self):
        error = PlaywrightTimeout(
            "Locator.fill: Timeout 30000ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='username']\")\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.LOCATOR_RESOLUTION
        assert result.locator_resolved is False
        assert result.action == "fill"

    def test_conditionally_mounted_element_also_classifies_as_locator_resolution(self):
        # Real capture from the async_delay diagnostic (Sprint 6B).
        # AddItemForm's confirmation is conditionally rendered — it
        # genuinely never resolves until ready, producing a message
        # Playwright cannot distinguish from a truly broken selector.
        # This is the EXPECTED, documented behavior (see Gap #14) —
        # this test protects that the parser doesn't try to guess a
        # distinction the message doesn't support.
        error = PlaywrightTimeout(
            "Locator.wait_for: Timeout 100ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='item-added-confirmation']\") to be visible\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.LOCATOR_RESOLUTION
        assert result.locator_resolved is False
        assert result.action == "wait_for"


@pytest.mark.unit
class TestActionabilityReasons:
    """
    Every message below is a verbatim capture from the Sprint 6B
    disabled/hidden/readonly (fill()) and unstable/overlaid (click())
    diagnostics. Each resolves the locator first, then reports one
    specific, distinct reason — the structural signal this whole model
    is built on.
    """

    def test_disabled_input_is_enabled_reason(self):
        error = PlaywrightTimeout(
            "Locator.fill: Timeout 100ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"#target\")\n"
            "    - locator resolved to <input disabled id=\"target\"/>\n"
            "    - fill(\"x\")\n"
            "  - attempting fill action\n"
            "    2 × waiting for element to be visible, enabled and editable\n"
            "      - element is not enabled\n"
            "    - retrying fill action\n"
            "    - waiting 20ms\n"
            "    - waiting for element to be visible, enabled and editable\n"
            "    - element is not enabled\n"
            "  - retrying fill action\n"
            "    - waiting 100ms\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.ACTIONABILITY
        assert result.locator_resolved is True
        assert result.actionability_reason == ActionabilityReason.ENABLED
        assert result.action == "fill"

    def test_hidden_input_is_visible_reason(self):
        error = PlaywrightTimeout(
            "Locator.fill: Timeout 100ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"#target\")\n"
            "    - locator resolved to <input id=\"target\"/>\n"
            "    - fill(\"x\")\n"
            "  - attempting fill action\n"
            "    2 × waiting for element to be visible, enabled and editable\n"
            "      - element is not visible\n"
            "    - retrying fill action\n"
            "    - waiting 20ms\n"
            "    - waiting for element to be visible, enabled and editable\n"
            "    - element is not visible\n"
            "  - retrying fill action\n"
            "    - waiting 100ms\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.ACTIONABILITY
        assert result.actionability_reason == ActionabilityReason.VISIBLE

    def test_readonly_input_is_editable_reason(self):
        error = PlaywrightTimeout(
            "Locator.fill: Timeout 100ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"#target\")\n"
            "    - locator resolved to <input readonly id=\"target\"/>\n"
            "    - fill(\"x\")\n"
            "  - attempting fill action\n"
            "    2 × waiting for element to be visible, enabled and editable\n"
            "      - element is not editable\n"
            "    - retrying fill action\n"
            "    - waiting 20ms\n"
            "    - waiting for element to be visible, enabled and editable\n"
            "    - element is not editable\n"
            "  - retrying fill action\n"
            "    - waiting 100ms\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.ACTIONABILITY
        assert result.actionability_reason == ActionabilityReason.EDITABLE

    def test_animating_element_is_stable_reason(self):
        # Captured with a deterministic requestAnimationFrame loop, not
        # CSS keyframes — the CSS version's default easing let click()
        # succeed by chance on the first diagnostic attempt (dwell
        # points near zero velocity). See LEARNINGS.md Sprint 6B for
        # why the deterministic rAF version was needed instead.
        error = PlaywrightTimeout(
            "Locator.click: Timeout 300ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"#target\")\n"
            "    - locator resolved to <button id=\"target\">Click me</button>\n"
            "  - attempting click action\n"
            "    2 × waiting for element to be visible, enabled and stable\n"
            "      - element is not stable\n"
            "    - retrying click action\n"
            "    - waiting 20ms\n"
            "    2 × waiting for element to be visible, enabled and stable\n"
            "      - element is not stable\n"
            "    - retrying click action\n"
            "      - waiting 100ms\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.ACTIONABILITY
        assert result.actionability_reason == ActionabilityReason.STABLE
        assert result.action == "click"

    def test_overlaid_element_is_receives_events_reason_with_blocking_element_named(self):
        # The richest of the five reasons — Playwright names the actual
        # blocking element, not just the condition.
        error = PlaywrightTimeout(
            "Locator.click: Timeout 200ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"#target\")\n"
            "    - locator resolved to <button id=\"target\">Click me</button>\n"
            "  - attempting click action\n"
            "    2 × waiting for element to be visible, enabled and stable\n"
            "      - element is visible, enabled and stable\n"
            "      - scrolling into view if needed\n"
            "      - done scrolling\n"
            "      - <div id=\"overlay\"></div> intercepts pointer events\n"
            "    - retrying click action\n"
            "    - waiting 20ms\n"
            "    - waiting for element to be visible, enabled and stable\n"
            "    - element is visible, enabled and stable\n"
            "    - scrolling into view if needed\n"
            "    - done scrolling\n"
            "    - <div id=\"overlay\"></div> intercepts pointer events\n"
            "  - retrying click action\n"
            "    - waiting 100ms\n"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.ACTIONABILITY
        assert result.actionability_reason == ActionabilityReason.RECEIVES_EVENTS
        assert result.blocking_element is not None
        assert "overlay" in result.blocking_element


@pytest.mark.unit
class TestReferenceCategory:
    """
    Dormant category (Gap #4) — these samples remain hand-crafted
    against Playwright's documented actionability vocabulary, carried
    over unchanged from Sprint 6A. Never confirmed against a live
    componentRemount.jsx run (Sprint 6A found no reproduction across
    four escalating attempts) — kept so the classifier still recognizes
    this shape correctly IF it is ever encountered for real, per the
    "dormant, not deleted" decision in LEARNINGS.md.
    """

    def test_not_attached_to_the_dom_is_reference(self):
        error = PlaywrightTimeout(
            "Locator.click: Timeout 10000ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='btn-login']\")\n"
            "  - locator resolved to <button>Log in</button>\n"
            "  - attempting click action\n"
            "  - element is not attached to the DOM\n"
            "  - retrying click action"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.REFERENCE

    def test_reference_substring_wins_over_locator_resolution(self):
        # Critical ordering case, carried over from Sprint 6A: a
        # detached-mid-action message also contains "waiting for
        # locator" — the more specific reference signal must win.
        error = PlaywrightTimeout(
            "Locator.click: Timeout 10000ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='btn-login']\")\n"
            "  - locator resolved to <button>Log in</button>\n"
            "  - element is not attached to the DOM"
        )
        result = parse_playwright_call_log(error)
        assert result.category == FailureCategory.REFERENCE