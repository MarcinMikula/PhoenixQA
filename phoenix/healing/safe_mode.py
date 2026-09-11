"""
safe_mode.py

Human-in-the-loop healing. Shows the full healing context in the
terminal — broken selector, error, proposed fix, confidence, reasoning —
then asks accept/reject. Per direct discussion: a bare accept/reject with
no context would be useless ("dobrze wiedzieć co się akceptuje").

IMPORTANT — pytest output capturing: this uses input(), which requires
running pytest with the -s flag (--capture=no). Without -s, pytest
swallows stdout/stdin during test execution and the prompt never reaches
the terminal — the test will hang with no visible explanation. This is
documented here AND in the README/LEARNINGS so it isn't a confusing
surprise on first run.
"""
from phoenix.ai.base_provider import HealingContext
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind, SelectorReplacement


def request_human_review(context: HealingContext, action: SelectorReplacement) -> bool:
    """
    Displays the full healing decision context and asks the human to
    accept or reject. Returns True if accepted, False if rejected.

    Deliberately verbose — see module docstring. A confidence number
    alone isn't enough to make an informed decision; the human needs to
    see the actual selector change and the model's stated reasoning.

    Caught via a real end-to-end run: a proposal with an EMPTY
    proposed_selector (the response_parser fallback for an unparseable
    LLM response — see response_parser.py) was accidentally accept-able
    by typing 'y'. The human did accept it, expecting "the LLM's fix,
    whatever it was" — but there was no fix, just a parse failure
    surfaced as a zero-confidence placeholder. The empty string then hit
    Playwright as `page.locator("").click()`, raising a confusing
    "Unexpected token" CSS parsing error instead of a clear message about
    what actually went wrong. There's nothing to accept here — this is
    not a human decision, it's a hard stop.
    """
    print("\n" + "=" * 70)
    print("🔥 PhoenixQA — Healing proposal requires review")
    print("=" * 70)
    print(f"Page URL:          {context.page_url}")
    print(f"Broken selector:   {context.broken_selector}")
    print(f"Error:             {context.error_message}")
    print("-" * 70)
    print(f"Proposed selector: {action.proposed_selector}")
    print(f"Confidence:        {action.confidence:.0%}")
    print(f"Reasoning:         {action.reasoning}")
    if action.alternative_selectors:
        print(f"Alternatives:      {', '.join(action.alternative_selectors)}")
    print("=" * 70)

    if not action.proposed_selector:
        print(
            "⚠️  No usable selector was proposed (LLM response could not be "
            "parsed). Nothing to accept — auto-rejecting. The original "
            "test failure will be reported."
        )
        return False

    while True:
        answer = input("Accept this fix and retry the action? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def request_human_review_actionability(context: HealingContext, action: ActionabilityStrategy) -> bool:
    """
    Sprint 8 (Option A, narrowed) — the ActionabilityStrategy counterpart
    to request_human_review() above. A separate function, not a branch
    inside the existing one — matches this project's own "divergence
    over unification" philosophy (separate collectors/prompts per
    failure type; this is the same instinct applied to the review UX).
    A human reviewing "wait 1200ms and retry the SAME action" needs to
    see a strategy and a wait time, not a proposed selector — showing
    an empty "Proposed selector:" line for every VISIBLE review would
    be confusing, not just cosmetically different.

    Scope: called only for ActionabilityReason.VISIBLE (see healer.py)
    — the two strategies that reason's prompt is restricted to,
    WAIT_AND_RETRY and NO_SAFE_RECOVERY, are both handled explicitly
    below. Any other ActionabilityStrategyKind reaching this function
    would be a Healer-level scope bug, not a human decision — printed
    plainly and auto-rejected, same "nothing to review" logic
    request_human_review() already applies to an empty proposed_selector.

    Also surfaces corrected_by_policy/original_strategy/policy_reason
    when set — see actionability_policy.py's docstring. A human
    reviewer benefits from seeing "the model said X, the policy
    corrected it to Y, because Z" just as much as an Autonomous Mode
    log entry does; hiding the correction would make the review LESS
    informed than the automated path.
    """
    print("\n" + "=" * 70)
    print("🔥 PhoenixQA — Actionability strategy requires review")
    print("=" * 70)
    print(f"Page URL:          {context.page_url}")
    print(f"Broken selector:   {context.broken_selector}")
    print(f"Error:             {context.error_message}")
    print(f"Actionability:     {action.reason.value if action.reason else 'unknown'}")
    print("-" * 70)
    strategy_name = action.strategy.value if action.strategy else "unknown"
    print(f"Proposed strategy: {strategy_name}")
    if action.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY:
        print(f"Suggested wait:    {action.suggested_wait_ms}ms")
    print(f"Confidence:        {action.confidence:.0%}")
    print(f"Reasoning:         {action.reasoning}")
    if action.corrected_by_policy:
        original = action.original_strategy.value if action.original_strategy else "unknown"
        print(f"⚠️  Policy correction: model proposed '{original}', "
              f"corrected to '{strategy_name}' — {action.policy_reason}")
    print("=" * 70)

    if action.strategy not in (
        ActionabilityStrategyKind.WAIT_AND_RETRY,
        ActionabilityStrategyKind.NO_SAFE_RECOVERY,
    ):
        print(
            f"⚠️  Strategy '{strategy_name}' is not supported for VISIBLE yet "
            f"(only wait_and_retry/no_safe_recovery are). Nothing to accept — "
            f"auto-rejecting."
        )
        return False

    if action.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY:
        print(
            "⚠️  Model determined there is no safe recovery — nothing to wait "
            "for. Auto-rejecting; the original test failure will be reported."
        )
        return False

    while True:
        answer = input("Accept this strategy and retry the action? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")