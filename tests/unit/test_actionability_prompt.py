"""
test_actionability_prompt.py

Unit tests for phoenix/ai/prompts/actionability_prompt.py. Two things
are worth protecting with tests, not just prose comments:

1. SYSTEM_PROMPT's content — specifically the self-consistency rule and
   the corrected examples added after a real live-run finding (see
   LEARNINGS.md "Confirmatory re-runs resolve A vs B"). A future edit
   silently dropping the self-consistency instruction, or reintroducing
   the original misleading example (which taught dismiss_blocker for an
   overlay shaped almost identically to the real, non-dismissible one),
   would be exactly the kind of regression that's invisible until the
   next live run — catching it here is cheap, the live run is not.
2. build_user_prompt()'s rendering logic — already partially exercised
   indirectly via test_ollama_provider.py, but tested directly here the
   same way prompt_templates.py's counterpart would be, so this module
   isn't the one piece of the actionability path without its own test
   file.
"""
import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.ai.prompts.actionability_prompt import SYSTEM_PROMPT, build_user_prompt
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory


def _make_context(collector_metadata=None):
    return HealingContext(
        broken_selector="[data-testid='btn-login']",
        error_message="Locator.click: intercepts pointer events",
        dom_snapshot="Target element:\n<button data-testid='btn-login'>",
        page_url="http://localhost:5173/",
        original_code="click",
        category=FailureCategory.ACTIONABILITY,
        actionability_reason=ActionabilityReason.RECEIVES_EVENTS,
        collector_metadata=collector_metadata or {},
    )


@pytest.mark.unit
class TestSystemPromptContent:
    def test_includes_self_consistency_check(self):
        # Added directly in response to a live-run finding: the model
        # repeatedly stated a blocker was "persistent"/"not transient"
        # and then chose wait_and_retry anyway. This instruction is the
        # fix — a future edit must not silently drop it.
        assert "SELF-CONSISTENCY" in SYSTEM_PROMPT
        assert "wait_and_retry" in SYSTEM_PROMPT

    def test_no_safe_recovery_example_matches_the_real_captured_overlay(self):
        # Regression guard for the original misleading example, which
        # taught dismiss_blocker for near-identical styling (position:
        # fixed, z-index: 9999, pointer-events: auto) to the real,
        # non-dismissible pointerEventsOverlay.jsx. The corrected
        # example must show no_safe_recovery for this exact shape.
        assert "chaos-pointer-events-overlay" in SYSTEM_PROMPT
        assert '"strategy": "no_safe_recovery"' in SYSTEM_PROMPT

    def test_includes_a_positive_dismiss_blocker_example_too(self):
        # The fix must not overcorrect into "always answer
        # no_safe_recovery" — a genuinely dismissible blocker (an actual
        # button) must still be demonstrated as a valid dismiss_blocker
        # case, or the model loses that capability entirely.
        assert '"strategy": "dismiss_blocker"' in SYSTEM_PROMPT
        assert "cookie-accept" in SYSTEM_PROMPT

    def test_blocking_element_field_asks_for_specific_affordance_not_whole_container(self):
        # The original prompt's JSON schema description said "the
        # blocking element's HTML if one was identified" — vague enough
        # to justify naming the entire overlay div. The revision must be
        # explicit that this field is for the specific dismiss control.
        assert "SPECIFIC dismiss-affordance element" in SYSTEM_PROMPT

    def test_still_forbids_force_not_allowed(self):
        assert "force_not_allowed" in SYSTEM_PROMPT
        assert "must never be the one you choose" in SYSTEM_PROMPT


@pytest.mark.unit
class TestBuildUserPrompt:
    def test_includes_target_and_call_log_blocker(self):
        context = _make_context(collector_metadata={
            "target_outer_html": "<button data-testid='btn-login'>Log in</button>",
            "target_bounding_box": {"x": 10, "y": 20, "width": 80, "height": 30},
            "blocking_element_from_call_log": "<div data-testid='chaos-pointer-events-overlay'>",
        })
        prompt = build_user_prompt(context)

        assert "btn-login" in prompt
        assert "chaos-pointer-events-overlay" in prompt
        assert "selector is CORRECT" in prompt

    def test_includes_dom_probe_confirmation_when_present(self):
        context = _make_context(collector_metadata={
            "blocking_element_outer_html": "<div data-testid='chaos-pointer-events-overlay'></div>",
            "blocking_element_bounding_box": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "blocking_element_computed_style": {"pointerEvents": "auto"},
        })
        prompt = build_user_prompt(context)

        assert "independently confirmed via a DOM probe" in prompt
        assert "pointerEvents" in prompt

    def test_honestly_states_when_dom_probe_found_nothing(self):
        # No blocking_element_outer_html in metadata — the collector's
        # own honesty principle (see actionability_collector.py) must
        # carry through to the prompt text, not silently omit the gap.
        context = _make_context(collector_metadata={})
        prompt = build_user_prompt(context)

        assert "No independent DOM-probe confirmation was found" in prompt