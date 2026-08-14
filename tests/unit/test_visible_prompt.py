"""
test_visible_prompt.py

Unit tests for phoenix/ai/prompts/visible_prompt.py. Same two-part
coverage as test_actionability_prompt.py: SYSTEM_PROMPT content itself
(self-consistency check, both examples, the explicit "never propose
dismiss_blocker" rule that's specific to this reason since there's no
separate blocker to dismiss) and build_user_prompt()'s rendering logic.
"""
import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.ai.prompts.visible_prompt import SYSTEM_PROMPT, build_user_prompt
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory


def _make_context(collector_metadata=None):
    return HealingContext(
        broken_selector="[data-testid='password-x7f2']",
        error_message="Locator.fill: Timeout 30000ms exceeded. ... element is not visible",
        dom_snapshot="Target element (exists in the DOM but is not visible):\n<input>",
        page_url="http://localhost:5173/",
        original_code="fill",
        category=FailureCategory.ACTIONABILITY,
        actionability_reason=ActionabilityReason.VISIBLE,
        collector_metadata=collector_metadata or {},
    )


@pytest.mark.unit
class TestSystemPromptContent:
    def test_includes_self_consistency_check(self):
        assert "SELF-CONSISTENCY" in SYSTEM_PROMPT
        assert "wait_and_retry" in SYSTEM_PROMPT

    def test_never_propose_dismiss_blocker_for_this_reason(self):
        # VISIBLE has no separate blocking element — the prompt must
        # explicitly forbid inventing one, unlike RECEIVES_EVENTS where
        # dismiss_blocker is a legitimate strategy.
        assert "Do NOT propose \"dismiss_blocker\"" in SYSTEM_PROMPT

    def test_still_forbids_force_not_allowed(self):
        assert "force_not_allowed" in SYSTEM_PROMPT
        assert "must never be the one you choose" in SYSTEM_PROMPT

    def test_includes_no_safe_recovery_example(self):
        assert '"strategy": "no_safe_recovery"' in SYSTEM_PROMPT

    def test_includes_wait_and_retry_example_grounded_in_an_observed_change(self):
        # The positive example must show an ACTUAL OBSERVED CHANGE
        # between t0 and t1 (not a declared CSS capability) — the
        # deliberate evidence-design correction made for this reason
        # (see actionability_collector.py's module docstring): a
        # declared transition/animation only proves capability, not
        # that a change is actually in progress or will resolve
        # anything.
        assert '"strategy": "wait_and_retry"' in SYSTEM_PROMPT
        assert "ACTUALLY CHANGED" in SYSTEM_PROMPT
        assert "visibility=hidden" in SYSTEM_PROMPT
        assert "visibility=visible" in SYSTEM_PROMPT

    def test_strategy_field_only_lists_two_options(self):
        # Unlike RECEIVES_EVENTS (three strategy options), VISIBLE's
        # JSON schema description should only ever mention the two
        # strategies actually valid for this reason.
        assert '"strategy": "one of: wait_and_retry, no_safe_recovery"' in SYSTEM_PROMPT


@pytest.mark.unit
class TestBuildUserPrompt:
    def test_includes_target_html_and_temporal_observation(self):
        context = _make_context(collector_metadata={
            "target_outer_html": '<input data-testid="password-x7f2" type="password">',
            "target_bounding_box": {"x": 10, "y": 60, "width": 200, "height": 30},
            "target_state_t0": {"visibility": "hidden", "display": "block", "opacity": "1"},
            "target_state_t1": {"visibility": "visible", "display": "block", "opacity": "1"},
            "observation_window_ms": 1200,
            "target_state_changed_during_observation": True,
        })
        prompt = build_user_prompt(context)

        assert "password-x7f2" in prompt
        assert "visibility" in prompt
        assert "1200" in prompt
        assert "True" in prompt
        assert "selector is CORRECT" in prompt

    def test_handles_missing_metadata_gracefully(self):
        context = _make_context(collector_metadata={})
        prompt = build_user_prompt(context)

        assert "not found" in prompt
        assert "not captured" in prompt
