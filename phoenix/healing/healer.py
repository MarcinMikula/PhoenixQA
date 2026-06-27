"""
healer.py
Orchestrator — intercepts Playwright failures, routes to Safe or Autonomous mode.

Integration with BasePage:
    BasePage.click()/fill() catch a Playwright exception → call
    Healer.attempt_heal() → get back a working selector → retry the action
    in the SAME test step (see direct discussion: "namierzenie błędu,
    pytanie o akceptację naprawy, naprawę, ponowienie testu od kroku z
    błędem" — confirmed flow, not a restart of the whole test).

Sprint 4 scope: Safe Mode only (HEALING_MODE=safe). Autonomous Mode
(Sprint 5) reuses the same ContextCollector → Provider pipeline but skips
the human review step — and MUST add stop conditions (max_attempts,
max_cost_per_test, max_time_per_heal) before it ships, per Gap #10
(LEARNINGS.md) — that's explicitly NOT optional hardening, it's a Sprint 5
blocking requirement.
"""
from playwright.sync_api import Page

from config.settings import Settings
from phoenix.ai.provider_factory import get_provider
from phoenix.collector.context_collector import ContextCollector
from phoenix.healing.decision_logger import log_decision
from phoenix.healing.safe_mode import request_human_review


class HealingRejectedError(Exception):
    """
    Raised when the human reviewer rejects a proposed fix. The original
    test failure is what should actually be reported — this exception
    exists so BasePage can distinguish "healing was attempted and
    declined" from "healing crashed," and let the ORIGINAL Playwright
    error surface to pytest rather than this one.
    """
    pass


class Healer:
    def __init__(self, page: Page, settings: Settings):
        self.page = page
        self.settings = settings
        self.provider = get_provider(settings)
        self.collector = ContextCollector(page)

    def attempt_heal(self, broken_selector: str, error: Exception, original_code: str) -> str:
        """
        Main entry point, called from BasePage on a Playwright exception.

        Returns the healed selector string if the human (Safe Mode) or
        the system (Autonomous Mode, Sprint 5) accepts a fix. Raises
        HealingRejectedError if the human declines — BasePage is expected
        to catch that and re-raise the ORIGINAL error, not this one, so
        pytest reports the real failure reason.
        """
        context = self.collector.collect(broken_selector, error, original_code)
        proposal = self.provider.analyze_failure(context)

        if self.settings.healing_mode == "autonomous":
            # Sprint 5 — NOT implemented yet. Loud failure here is
            # deliberate: Autonomous Mode without stop conditions (Gap
            # #10) must not silently fall through to some default
            # behavior. See module docstring.
            raise NotImplementedError(
                "Autonomous Mode is Sprint 5 scope and requires stop "
                "conditions (max_attempts/cost/time) before it can ship — "
                "see LEARNINGS.md Gap #10. Set HEALING_MODE=safe for now."
            )

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
            log_decision(context, proposal, accepted=False)
            raise HealingRejectedError(
                f"Healing proposal was empty or zero-confidence for broken "
                f"selector '{broken_selector}' — likely a malformed LLM "
                f"response (see decision log for raw_response). Auto-rejected "
                f"without prompting, nothing to review."
            )

        accepted = request_human_review(context, proposal)
        log_decision(context, proposal, accepted)

        if not accepted:
            raise HealingRejectedError(
                f"Human rejected proposed fix '{proposal.proposed_selector}' "
                f"for broken selector '{broken_selector}'"
            )

        return proposal.proposed_selector
