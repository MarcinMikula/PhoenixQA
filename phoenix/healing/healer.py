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
"""
from playwright.sync_api import Page

from config.settings import Settings
from phoenix.ai.provider_factory import get_provider
from phoenix.collector.context_collector import ContextCollector
from phoenix.healing.autonomous_policy import AutonomousPolicy, HealingBudget, HealLifecycleTimer
from phoenix.healing.decision_logger import log_decision
from phoenix.healing.safe_mode import request_human_review


class HealingRejectedError(Exception):
    """
    Raised when a proposed fix is declined — either by a human (Safe
    Mode) or by policy (Autonomous Mode: confidence below threshold, or
    an empty/zero-confidence proposal with nothing to evaluate). The
    ORIGINAL test failure is what should actually be reported — this
    exception exists so BasePage can distinguish "healing was attempted
    and declined" from "healing crashed," and let the original
    Playwright error surface to pytest rather than this one.
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

        proposal = result.proposal

        if not proposal.proposed_selector or proposal.confidence <= 0.0:
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
                context, proposal, accepted=False, mode="safe",
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

        accepted = request_human_review(context, proposal)
        log_decision(
            context, proposal, accepted, mode="safe",
            provider=self.settings.ai_provider,
            elapsed_ms=result.elapsed_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

        if not accepted:
            raise HealingRejectedError(
                f"Human rejected proposed fix '{proposal.proposed_selector}' "
                f"for broken selector '{broken_selector}'"
            )

        return proposal.proposed_selector

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

        proposal = result.proposal
        self.budget.record_attempt(
            broken_selector,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        log_decision(
            context,
            proposal,
            accepted=(proposal.confidence >= self.policy.min_confidence),
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

        if not proposal.proposed_selector or proposal.confidence < self.policy.min_confidence:
            raise HealingRejectedError(
                f"Autonomous policy rejected proposed fix '{proposal.proposed_selector}' "
                f"for broken selector '{broken_selector}': confidence "
                f"{proposal.confidence:.2f} below policy threshold "
                f"{self.policy.min_confidence:.2f}"
            )

        return proposal.proposed_selector
