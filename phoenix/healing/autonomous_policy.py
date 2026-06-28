"""
autonomous_policy.py

Sprint 5 — Gap #10 resolution. Two separate concerns, deliberately kept
apart:

  AutonomousPolicy  — the LIMITS (configuration, set once per run)
  HealingBudget     — the CONSUMPTION (running totals, mutated as
                       healing attempts happen)

This split mirrors why confidence threshold isn't a hardcoded constant
in Healer (see LEARNINGS.md "Decision: confidence threshold is a
configurable policy") — Safe Mode and Autonomous Mode share the same
collect→analyze pipeline, differing only in policy. A policy object is
also what makes max_attempts/tokens/time testable in isolation, without
needing a live Healer to exercise the limit logic.

Budget is tracked in TOKENS and TIME, never currency — see LEARNINGS.md
"Decision: budget in tokens/time, never in currency" for why a dollar
figure doesn't belong in this codebase at all.
"""
import time
from dataclasses import dataclass, field


@dataclass
class AutonomousPolicy:
    """
    Configuration for Autonomous Mode — the limits a HealingSession must
    respect. One instance per test run (or per Healer instance); does
    not mutate during the run.
    """
    min_confidence: float = 0.75
    max_attempts_total: int = 5
    max_input_tokens: int = 50_000
    max_output_tokens: int = 10_000
    max_time_per_heal_ms: int = 60_000  # wraps the FULL collect+analyze+apply+retry lifecycle


@dataclass
class HealingBudget:
    """
    Running consumption totals for one HealingSession (i.e. one test
    run). Per-selector attempt counts are tracked separately as a
    diagnostic side-channel — see attempts_by_selector — but
    attempts_total against policy.max_attempts_total is the actual stop
    condition (see LEARNINGS.md "Decision: max_attempts is
    total-per-session").
    """
    policy: AutonomousPolicy
    attempts_total: int = 0
    attempts_by_selector: dict = field(default_factory=dict)
    input_tokens_used: int = 0
    output_tokens_used: int = 0

    def record_attempt(self, selector: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """
        Called once per healing attempt, regardless of outcome —
        recording happens even for a rejected or failed attempt, since
        the budget was still spent.
        """
        self.attempts_total += 1
        self.attempts_by_selector[selector] = self.attempts_by_selector.get(selector, 0) + 1
        self.input_tokens_used += input_tokens or 0
        self.output_tokens_used += output_tokens or 0

    def attempts_for(self, selector: str) -> int:
        """Diagnostic accessor — how many times THIS selector has been
        attempted in this session. Not itself a limit; see class docstring."""
        return self.attempts_by_selector.get(selector, 0)

    def exceeded(self) -> bool:
        """
        True if any limit has already been hit BEFORE attempting another
        heal. Checked at the start of attempt_heal(), so a session that's
        out of budget never even calls the LLM for one more try.
        """
        return (
            self.attempts_total >= self.policy.max_attempts_total
            or self.input_tokens_used >= self.policy.max_input_tokens
            or self.output_tokens_used >= self.policy.max_output_tokens
        )

    def reason_exceeded(self) -> str:
        """Human-readable explanation of WHICH limit was hit — used in
        HealingLimitExceededError messages so a CI log says exactly why,
        not just that some limit somewhere was exceeded."""
        if self.attempts_total >= self.policy.max_attempts_total:
            return f"max_attempts_total ({self.policy.max_attempts_total}) reached"
        if self.input_tokens_used >= self.policy.max_input_tokens:
            return f"max_input_tokens ({self.policy.max_input_tokens}) reached"
        if self.output_tokens_used >= self.policy.max_output_tokens:
            return f"max_output_tokens ({self.policy.max_output_tokens}) reached"
        return "no limit currently exceeded"


class HealLifecycleTimer:
    """
    Measures the FULL collect()+analyze()+apply()+retry() lifecycle for
    one healing attempt, not just the LLM call — see LEARNINGS.md
    "Decision: max_time_per_heal wraps the full lifecycle." CI cares
    about total time spent on a healing attempt, regardless of how that
    time is split between context collection, inference, and retry.

    Usage:
        timer = HealLifecycleTimer()
        with timer:
            ... collect, analyze, apply, retry ...
        if timer.elapsed_ms > policy.max_time_per_heal_ms:
            raise HealingLimitExceededError(...)
    """
    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed_ms = int((time.monotonic() - self._start) * 1000)
        return False  # never suppress exceptions raised inside the block
