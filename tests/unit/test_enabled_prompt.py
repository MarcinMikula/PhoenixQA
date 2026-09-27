"""
test_enabled_prompt.py

Unit tests for phoenix/ai/prompts/enabled_prompt.py. Same two-part
coverage as test_visible_prompt.py, which this reason's prompt mirrors
directly (see enabled_prompt.py's own docstring for why): SYSTEM_PROMPT
content itself (self-consistency check, both examples, the explicit
"never propose dismiss_blocker" rule) and build_user_prompt()'s
rendering logic.
"""
import pytest

from phoenix.ai.base_provider import HealingContext
from phoenix.ai.prompts.enabled_prompt import SYSTEM_PROMPT, build_user_prompt
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory


def _make_context(collector_metadata=None):
    return HealingContext(
        broken_selector="[data-testid='btn-login-x7f2']",
        error_message="Locator.click: Timeout 10000ms exceeded. ... element is not enabled",
        dom_snapshot="Target element (exists in the DOM but is not enabled):\n<button>",
        page_url="http://localhost:5173/",
        original_code="click",
        category=FailureCategory.ACTIONABILITY,
        actionability_reason=ActionabilityReason.ENABLED,
        collector_metadata=collector_metadata or {},
    )


@pytest.mark.unit
class TestSystemPromptContent:
    def test_includes_self_consistency_check(self):
        assert "SELF-CONSISTENCY" in SYSTEM_PROMPT
        assert "wait_and_retry" in SYSTEM_PROMPT

    def test_never_propose_dismiss_blocker_for_this_reason(self):
        # ENABLED has no separate blocking element, same as VISIBLE —
        # the prompt must explicitly forbid inventing one.
        assert 'Do NOT propose "dismiss_blocker"' in SYSTEM_PROMPT

    def test_still_forbids_force_not_allowed(self):
        assert "force_not_allowed" in SYSTEM_PROMPT
        assert "must never be the one you choose" in SYSTEM_PROMPT

    def test_includes_no_safe_recovery_example(self):
        assert '"strategy": "no_safe_recovery"' in SYSTEM_PROMPT

    def test_includes_wait_and_retry_example_grounded_in_an_observed_change(self):
        # Same evidence-design principle as VISIBLE's prompt: the
        # positive example must show an ACTUAL OBSERVED CHANGE in
        # `disabled` between t0 and t1, not a declared capability.
        assert '"strategy": "wait_and_retry"' in SYSTEM_PROMPT
        assert "ACTUALLY CHANGED" in SYSTEM_PROMPT
        assert "disabled=true" in SYSTEM_PROMPT
        assert "disabled=false" in SYSTEM_PROMPT

    def test_strategy_field_only_lists_two_options(self):
        # Unlike RECEIVES_EVENTS (three strategy options), ENABLED's
        # JSON schema description should only ever mention the two
        # strategies actually valid for this reason.
        assert '"strategy": "one of: wait_and_retry, no_safe_recovery"' in SYSTEM_PROMPT

    def test_explicitly_says_selector_is_correct(self):
        # Same as VISIBLE — unlike LOCATOR_RESOLUTION's prompt, this
        # one must actively discourage proposing a new selector, since
        # the model has no other prompt telling it selectors CAN be
        # wrong in this context.
        assert "nothing to rename" in SYSTEM_PROMPT


@pytest.mark.unit
class TestBuildUserPrompt:
    def test_includes_target_html_and_temporal_observation(self):
        context = _make_context(collector_metadata={
            "target_outer_html": '<button data-testid="btn-login-x7f2">Log in</button>',
            "target_state_t0": {"disabled": True},
            "target_state_t1": {"disabled": False},
            "observation_window_ms": 1200,
            "target_state_changed_during_observation": True,
        })
        prompt = build_user_prompt(context)

        assert "btn-login-x7f2" in prompt
        assert "disabled" in prompt
        assert "1200" in prompt
        assert "True" in prompt
        assert "selector is CORRECT" in prompt

    def test_handles_missing_metadata_gracefully(self):
        context = _make_context(collector_metadata={})
        prompt = build_user_prompt(context)

        assert "not found" in prompt
        assert "not captured" in prompt