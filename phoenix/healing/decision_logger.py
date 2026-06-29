"""
decision_logger.py

Sprint 4 scope: simple append-only log file, NOT a database. Per direct
discussion — full SQLite history_store.py is Sprint 6 work, once Gap #1
(healing correctness definition) is resolved and we know what the schema
actually needs to capture. Building the real schema now would mean
guessing at structure twice.

Format: JSON Lines (one JSON object per line) — human-readable enough to
`cat` and skim during a test run review, but still structured enough to
mechanically parse later when Sprint 6 migrates this into SQLite. Per
direct discussion: "case z błędem miał fajnie rozbudowany log, aby
użytkownik po zakończonym teście mógł dobrze prześledzić, ocenić
diagnozę/naprawę" — every field needed for that post-hoc review is
captured here, including the raw LLM response text (essential for
diagnosing parse failures — without it, a "JSON parse error" message
alone gives no way to see WHAT the model actually returned).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from phoenix.ai.base_provider import HealingContext, HealingProposal

DEFAULT_LOG_PATH = "healing_decisions.log"


def log_decision(
    context: HealingContext,
    proposal: HealingProposal,
    accepted: bool,
    mode: str = "safe",
    provider: str = None,
    elapsed_ms: int = None,
    input_tokens: int = None,
    output_tokens: int = None,
    attempt: int = None,
    log_path: str = DEFAULT_LOG_PATH,
) -> None:
    """
    Appends one JSON line capturing the full decision — everything a
    human would need to review later: what broke, what was proposed, what
    was decided, and why. This is deliberately NOT just "accepted: true/false"
    — see module docstring.

    mode must be passed explicitly by the caller ("safe" or "autonomous")
    — caught via a real live run: this previously hardcoded "safe"
    unconditionally, so every Autonomous Mode decision was silently
    mislabeled in the log. Harmless-looking in isolation, but would have
    quietly corrupted any future Safe-vs-Autonomous analysis (Sprint 6/7
    Healing History, Sprint 8 benchmark) built on this field.

    provider/elapsed_ms/input_tokens/output_tokens/attempt are all
    optional and default to None — Safe Mode call sites that don't have
    ProviderResult timing/token data on hand (or callers from before this
    was added) still log a valid entry, just with these fields null
    rather than fabricated. See LEARNINGS.md "Future consideration:
    richer decision log fields" — these were already being computed
    in-memory (ProviderResult, HealingBudget) and simply discarded after
    budget tracking instead of also being logged; this is pure wiring,
    not new logic.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "page_url": context.page_url,
        "broken_selector": context.broken_selector,
        "error_message": context.error_message,
        "failure_type": context.failure_type.value if context.failure_type else None,
        "original_code": context.original_code,
        "proposed_selector": proposal.proposed_selector,
        "confidence": proposal.confidence,
        "reasoning": proposal.reasoning,
        "alternative_selectors": proposal.alternative_selectors,
        "raw_response": proposal.raw_response,
        "accepted": accepted,
        "mode": mode,
        "provider": provider,
        "elapsed_ms": elapsed_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "attempt": attempt,
    }

    log_file = Path(log_path)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
