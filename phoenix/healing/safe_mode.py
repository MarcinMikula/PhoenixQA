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
from phoenix.healing.actions import SelectorReplacement



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
"""
healer.py
Orchestrator — intercepts Playwright failures, routes to Safe or Autonomous mode.

Integration with BasePage:
    BasePage.click()/fill() catch a Playwright exception → call
    Healer.attempt_heal() → get back a working selector → retry the action
    in the SAME test step (see direct discussion: "namierzenie błędu,
    pytanie o akceptację naprawy, naprawę, ponowienie testu od kroku z
    błędem" — confirmed flow, not a restart of the whole test).

Sprint 5: Autonomous Mode implemented alongside Safe Mode. Both share the
SAME collect→analyze pipeline; they differ only in what happens after a
proposal comes back — Safe Mode asks a human, Autonomous Mode checks a
policy (confidence threshold + budget) and decides on its own.

IMPORTANT — what Autonomous Mode does NOT do (see LEARNINGS.md Gap #11
and "Resolved: where does correctness validation belong?"): it only
verifies the action could be TECHNICALLY retried (selector resolved,
retry didn't raise). It does NOT judge whether the resulting application
behavior was business-correct (e.g. "did login actually succeed"). That
stays the test's own responsibility, same as Safe Mode, same as
Playwright's own click()/fill() never judging business outcomes either.

Sprint 6B (decision) — HealingAction migration: `result.proposal` is now
`result.action`, typed as `HealingAction`. Only `SelectorReplacement` is
consumed end-to-end today — `ActionabilityStrategy` is produced by
`OllamaProvider` for `RECEIVES_EVENTS` and `VISIBLE` (Sprint 6B, both
live-verified) but is still explicitly rejected by `Healer` via an
`isinstance(action, SelectorReplacement)` check — no execution exists
yet. `RetryStrategy` (the dormant `FailureCategory.REFERENCE`) remains
declared-only in `phoenix/healing/actions.py`. Both `_attempt_heal_safe`
and `_attempt_heal_autonomous` reject any non-`SelectorReplacement`
action rather than assuming one — deliberate, not an oversight: nothing
in `Healer` yet knows how to retry a wait/dismiss strategy the way it
knows how to retry a healed selector.

Sprint 8 (Option A, narrowed) — that changes for ONE case:
`ActionabilityReason.VISIBLE`, and only its two prompt-restricted
strategies (`WAIT_AND_RETRY`/`NO_SAFE_RECOVERY`; see
`phoenix/ai/prompts/visible_prompt.py`). Decided per direct discussion,
after Sprint 8's baseline comparison held at 8/8 and a genuine near-tie
test (`ticket_row_ambiguity`, Gap #16) was investigated and
deprioritized as not worth pursuing further right now. Deliberately
narrow: `RECEIVES_EVENTS` is UNCHANGED, still rejected outright — this
is not a general "Healer now executes actionability strategies"
change. `attempt_heal()`'s return contract stays a bare selector string
(no `BasePage` changes): for `WAIT_AND_RETRY`, `Healer` waits
internally (`page.wait_for_timeout()`, capped at
`MAX_ACTIONABILITY_WAIT_MS`) and returns the ORIGINAL, unchanged
`broken_selector` — the selector was never the problem, so there is no
new one to substitute; `BasePage`'s existing single retry call picks up
from there unmodified. For `NO_SAFE_RECOVERY`, there is nothing to
retry — raises `HealingRejectedError`, same exception family as every
other declined fix.
"""
from playwright.sync_api import Page

from config.settings import Settings
from phoenix.ai.provider_factory import get_provider
from phoenix.collector.context_collector import ContextCollector
from phoenix.collector.failure_classifier import ActionabilityReason
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind, SelectorReplacement
from phoenix.healing.autonomous_policy import AutonomousPolicy, HealingBudget, HealLifecycleTimer
from phoenix.healing.decision_logger import log_decision
from phoenix.healing.safe_mode import request_human_review, request_human_review_actionability

# Sprint 8 (Option A, narrowed) tuning constants. A malformed or
# hallucinated suggested_wait_ms from the LLM must not become an
# unbounded sleep — this is the same "name the stop condition
# explicitly" discipline as AutonomousPolicy's other limits (see
# LEARNINGS.md Gap #10). Sprint 6B's live-verified VISIBLE ground-truth
# scenarios used 1200ms; 5000ms is a generous but bounded ceiling above
# that, not a guess.
MAX_ACTIONABILITY_WAIT_MS = 5000
DEFAULT_ACTIONABILITY_WAIT_MS = 1000  # used when suggested_wait_ms is missing/non-positive


class HealingRejectedError(Exception):
    """
    Raised when a proposed fix is declined — either by a human (Safe
    Mode), by policy (Autonomous Mode: confidence below threshold, or
    an empty/zero-confidence proposal with nothing to evaluate), or
    because the provider returned a HealingAction type Healer doesn't
    support yet (Sprint 6B onward). The ORIGINAL test failure is what
    should actually be reported — this exception exists so BasePage can
    distinguish "healing was attempted and declined" from "healing
    crashed," and let the original Playwright error surface to pytest
    rather than this one.
    """
    pass


class HealingLimitExceededError(Exception):
    """
    Raised when Autonomous Mode stops healing because a budget limit
    (attempts/tokens/time) was exhausted — NOT because the LLM gave a
    bad answer. Deliberately a distinct type from HealingRejectedError:
    "the system ran out of budget" and "the model proposed something
    bad" are different failure classes, and collapsing them into one
    exception would make CI failure reports far less actionable (see
    LEARNINGS.md "Decision: three distinct exception types, not one").
    """
    pass


class HealingFailedError(Exception):
    """
    Raised when the healing pipeline itself crashes — a provider/API
    exception (network error, malformed request, Ollama unreachable,
    etc.) rather than a considered rejection. Distinguishes "the attempt
    to heal blew up" from "healing was attempted and declined" — see
    HealingRejectedError and HealingLimitExceededError docstrings for
    the other two members of this three-way split.
    """
    pass


class Healer:
    def __init__(self, page: Page, settings: Settings, policy: AutonomousPolicy = None):
        self.page = page
        self.settings = settings
        self.provider = get_provider(settings)
        self.collector = ContextCollector(page)
        # One budget per Healer instance — in practice, one per BasePage,
        # which in practice means one per test (see base_page.py's lazy
        # _get_healer()). A fresh test gets a fresh budget; attempts
        # don't leak across tests.
        self.policy = policy or AutonomousPolicy(
            min_confidence=settings.autonomous_min_confidence,
            max_attempts_total=settings.autonomous_max_attempts_total,
            max_input_tokens=settings.autonomous_max_input_tokens,
            max_output_tokens=settings.autonomous_max_output_tokens,
            max_time_per_heal_ms=settings.autonomous_max_time_per_heal_ms,
        )
        self.budget = HealingBudget(policy=self.policy)

    def attempt_heal(self, broken_selector: str, error: Exception, original_code: str) -> str:
        """
        Main entry point, called from BasePage on a Playwright exception.
        Routes to Safe Mode or Autonomous Mode based on settings.healing_mode.

        Returns the healed selector string on success. Raises one of
        HealingRejectedError / HealingLimitExceededError / HealingFailedError
        otherwise — BasePage is expected to catch all three and re-raise
        the ORIGINAL error, not these, so pytest reports the real failure.
        """
        if self.settings.healing_mode == "autonomous":
            return self._attempt_heal_autonomous(broken_selector, error, original_code)
        return self._attempt_heal_safe(broken_selector, error, original_code)

    def _attempt_heal_safe(self, broken_selector: str, error: Exception, original_code: str) -> str:
        try:
            context = self.collector.collect(broken_selector, error, original_code)
            result = self.provider.analyze_failure(context)
        except Exception as e:
            raise HealingFailedError(
                f"Healing pipeline raised an exception while analyzing "
                f"broken selector '{broken_selector}': {e}"
            ) from e

        action = result.action

        if isinstance(action, ActionabilityStrategy) and action.reason == ActionabilityReason.VISIBLE:
            return self._execute_visible_strategy_safe(context, action, result)

        if not isinstance(action, SelectorReplacement):
            # Only SelectorReplacement is implemented end-to-end today —
            # see module docstring. Fail loudly rather than silently
            # treating an unsupported action as a selector replacement,
            # which would crash on missing attributes further down.
            raise HealingRejectedError(
                f"Healer does not yet support {type(action).__name__} actions "
                f"for broken selector '{broken_selector}' — only SelectorReplacement "
                f"is implemented."
            )

        if not action.proposed_selector or action.confidence <= 0.0:
            # Caught via a real end-to-end run: a parse failure (e.g.
            # truncated JSON) produces a fallback proposal with an empty
            # selector and zero confidence — see response_parser.py's
            # _fallback_proposal(). Asking a human "accept this fix?" for
            # an empty string isn't a real decision; answering "y" by
            # habit led straight into Locator(""), a CSS parse error
            # that has nothing to do with the original failure. This
            # case is auto-rejected before the human is even asked —
            # there's nothing to review.
            log_decision(
                context, action, accepted=False, mode="safe",
                provider=self.settings.ai_provider,
                elapsed_ms=result.elapsed_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            raise HealingRejectedError(
                f"Healing proposal was empty or zero-confidence for broken "
                f"selector '{broken_selector}' — likely a malformed LLM "
                f"response (see decision log for raw_response). Auto-rejected "
                f"without prompting, nothing to review."
            )

        accepted = request_human_review(context, action)
        log_decision(
            context, action, accepted, mode="safe",
            provider=self.settings.ai_provider,
            elapsed_ms=result.elapsed_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

        if not accepted:
            raise HealingRejectedError(
                f"Human rejected proposed fix '{action.proposed_selector}' "
                f"for broken selector '{broken_selector}'"
            )

        return action.proposed_selector

    def _attempt_heal_autonomous(self, broken_selector: str, error: Exception, original_code: str) -> str:
        """
        Sprint 5. Three checks happen in this order, each able to stop
        the attempt before the next one runs:

        1. Budget check BEFORE calling the LLM at all — a session that's
           already out of budget shouldn't spend one more token finding
           that out (see LEARNINGS.md: checked at the start, not after).
        2. Full lifecycle timing via HealLifecycleTimer — wraps
           collect+analyze, so a slow provider call counts against
           max_time_per_heal_ms even though the timer started before any
           LLM call was made.
        3. Confidence gate via self.policy.min_confidence — Autonomous
           Mode has no human to show a low-confidence proposal to, so an
           insufficiently confident proposal is rejected the same way an
           empty one would be.

        Deliberately NOT a 4th check: no business/correctness validation
        of the retried action's outcome — see module docstring and
        LEARNINGS.md Gap #11.
        """
        if self.budget.exceeded():
            raise HealingLimitExceededError(
                f"Cannot attempt healing for '{broken_selector}': "
                f"{self.budget.reason_exceeded()}"
            )

        timer = HealLifecycleTimer()
        try:
            with timer:
                context = self.collector.collect(broken_selector, error, original_code)
                result = self.provider.analyze_failure(context)
        except Exception as e:
            # A crash still consumes an attempt — it was still an
            # attempt, even though it produced no usable proposal.
            self.budget.record_attempt(broken_selector)
            raise HealingFailedError(
                f"Healing pipeline raised an exception while analyzing "
                f"broken selector '{broken_selector}': {e}"
            ) from e

        action = result.action
        self.budget.record_attempt(
            broken_selector,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

        if isinstance(action, ActionabilityStrategy) and action.reason == ActionabilityReason.VISIBLE:
            return self._execute_visible_strategy_autonomous(context, action, result, timer)

        if not isinstance(action, SelectorReplacement):
            # Budget is already spent above — a real attempt happened,
            # even though Healer can't act on this result type yet.
            raise HealingRejectedError(
                f"Healer does not yet support {type(action).__name__} actions "
                f"for broken selector '{broken_selector}' — only SelectorReplacement "
                f"is implemented."
            )

        log_decision(
            context,
            action,
            accepted=(action.confidence >= self.policy.min_confidence),
            mode="autonomous",
            provider=self.settings.ai_provider,
            # Full collect+analyze lifecycle, not just the LLM call —
            # matches what max_time_per_heal_ms actually measures (see
            # method docstring point 2), so the logged number is the
            # same one the budget check below compares against.
            elapsed_ms=timer.elapsed_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            attempt=self.budget.attempts_for(broken_selector),
        )

        if timer.elapsed_ms > self.policy.max_time_per_heal_ms:
            raise HealingLimitExceededError(
                f"Healing for '{broken_selector}' took {timer.elapsed_ms}ms, "
                f"exceeding max_time_per_heal_ms ({self.policy.max_time_per_heal_ms}ms)"
            )

        if not action.proposed_selector or action.confidence < self.policy.min_confidence:
            raise HealingRejectedError(
                f"Autonomous policy rejected proposed fix '{action.proposed_selector}' "
                f"for broken selector '{broken_selector}': confidence "
                f"{action.confidence:.2f} below policy threshold "
                f"{self.policy.min_confidence:.2f}"
            )

        return action.proposed_selector

    def _wait_and_return_original(self, broken_selector: str, action: ActionabilityStrategy) -> str:
        """
        Sprint 8 (Option A, narrowed). The actual "execution" of a
        WAIT_AND_RETRY strategy — waits, then hands back the SAME
        selector that failed. There is no new selector to substitute:
        the original one was never wrong, it just wasn't actionable
        yet. `BasePage`'s existing single retry call does the rest
        unmodified — this is the entire reason `attempt_heal()`'s
        return contract didn't need to change (see module docstring).

        Caller is responsible for confirming `action.strategy ==
        WAIT_AND_RETRY` before calling this — it always waits, it does
        not itself branch on strategy kind.
        """
        wait_ms = action.suggested_wait_ms
        if not wait_ms or wait_ms <= 0:
            wait_ms = DEFAULT_ACTIONABILITY_WAIT_MS
        wait_ms = min(wait_ms, MAX_ACTIONABILITY_WAIT_MS)
        self.page.wait_for_timeout(wait_ms)
        return broken_selector

    def _execute_visible_strategy_safe(self, context, action: ActionabilityStrategy, result) -> str:
        """
        Safe Mode counterpart to `_attempt_heal_safe`'s SelectorReplacement
        path, for ActionabilityReason.VISIBLE only (see module docstring
        and `request_human_review_actionability()`'s own docstring for
        the full scope reasoning). `request_human_review_actionability()`
        already auto-rejects (no prompt) for NO_SAFE_RECOVERY and for any
        strategy kind outside the two VISIBLE supports — by the time
        `accepted` is True here, `action.strategy` is guaranteed to be
        WAIT_AND_RETRY, but the explicit check below stays anyway rather
        than relying on that as an unstated contract.
        """
        accepted = request_human_review_actionability(context, action)
        log_decision(
            context, action, accepted, mode="safe",
            provider=self.settings.ai_provider,
            elapsed_ms=result.elapsed_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

        if not accepted:
            strategy_name = action.strategy.value if action.strategy else "unknown"
            raise HealingRejectedError(
                f"Human rejected actionability strategy '{strategy_name}' "
                f"for broken selector '{context.broken_selector}'"
            )

        if action.strategy != ActionabilityStrategyKind.WAIT_AND_RETRY:
            raise HealingRejectedError(
                f"Accepted strategy '{action.strategy}' has no execution path "
                f"yet — only wait_and_retry is implemented for VISIBLE."
            )

        return self._wait_and_return_original(context.broken_selector, action)

    def _execute_visible_strategy_autonomous(
        self, context, action: ActionabilityStrategy, result, timer: HealLifecycleTimer
    ) -> str:
        """
        Autonomous Mode counterpart, mirroring `_attempt_heal_autonomous`'s
        SelectorReplacement path: log first (so a rejected/limit-exceeded
        attempt is still on record), then the same two gates that path
        already applies — full-lifecycle time budget, then confidence
        threshold — plus a strategy-kind check specific to this path,
        since NO_SAFE_RECOVERY/anything else has nothing to execute even
        at full confidence.
        """
        strategy_ok = action.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY
        log_decision(
            context,
            action,
            accepted=(strategy_ok and action.confidence >= self.policy.min_confidence),
            mode="autonomous",
            provider=self.settings.ai_provider,
            elapsed_ms=timer.elapsed_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            attempt=self.budget.attempts_for(context.broken_selector),
        )

        if timer.elapsed_ms > self.policy.max_time_per_heal_ms:
            raise HealingLimitExceededError(
                f"Healing for '{context.broken_selector}' took {timer.elapsed_ms}ms, "
                f"exceeding max_time_per_heal_ms ({self.policy.max_time_per_heal_ms}ms)"
            )

        if not strategy_ok:
            strategy_name = action.strategy.value if action.strategy else "unknown"
            raise HealingRejectedError(
                f"Autonomous policy has nothing to execute for actionability "
                f"strategy '{strategy_name}' on broken selector "
                f"'{context.broken_selector}' — only wait_and_retry is executable."
            )

        if action.confidence < self.policy.min_confidence:
            raise HealingRejectedError(
                f"Autonomous policy rejected actionability strategy "
                f"'{action.strategy.value}' for broken selector "
                f"'{context.broken_selector}': confidence {action.confidence:.2f} "
                f"below policy threshold {self.policy.min_confidence:.2f}"
            )

        return self._wait_and_return_original(context.broken_selector, action)