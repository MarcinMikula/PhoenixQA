"""
decision_logger.py

Sprint 4 scope: simple append-only log file, NOT a database. Per direct
discussion — full SQLite history_store.py is Sprint 6 work, once Gap #1
(healing correctness definition) is resolved and we know what the schema
actually needs to capture. Building the real schema now would mean
guessing at structure twice.

Format: JSON Lines (one JSON object per line) — human-readable enough to
`cat` and skim during a test run review, but still structured enough to
mechanically parse later when Sprint 6 migrates this into SQLite.

Sprint 6B (decision): failure_type (a single flat string) is replaced by
failure_category + actionability_reason (matching HealingContext's new
fields) plus a derived, denormalized failure_label
(e.g. "actionability:stable") purely for human/dashboard readability —
not a second source of truth.

Sprint 6B (decision) — HealingAction migration: the `proposal` parameter
is renamed `action` and typed as `HealingAction` — today, always a
SelectorReplacement, since Healer guards against any other HealingAction
subtype before ever calling this function (see healer.py). Field access
below (`action.proposed_selector` etc.) is intentionally
SelectorReplacement-specific for that reason, not written generically —
generalizing this is a real, future task once ActionabilityStrategy
actually reaches this function, not something to guess at now.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from phoenix.ai.base_provider import HealingContext
from phoenix.healing.actions import HealingAction

DEFAULT_LOG_PATH = "healing_decisions.log"


def _failure_label(context: HealingContext) -> str:
    """
    Denormalized, human-readable convenience field —
    "actionability:stable", or just "locator_resolution" when there's no
    reason. Exists for log-reading and the eventual Allure dashboard's
    grouping/filtering; category + actionability_reason remain the real
    source of truth.
    """
    if context.actionability_reason is not None:
        return f"{context.category.value}:{context.actionability_reason.value}"
    return context.category.value


def log_decision(
    context: HealingContext,
    action: HealingAction,
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
    mislabeled in the log.

    provider/elapsed_ms/input_tokens/output_tokens/attempt are all
    optional and default to None — Safe Mode call sites that don't have
    ProviderResult timing/token data on hand still log a valid entry,
    just with these fields null rather than fabricated.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "page_url": context.page_url,
        "broken_selector": context.broken_selector,
        "error_message": context.error_message,
        "failure_category": context.category.value if context.category else None,
        "actionability_reason": context.actionability_reason.value if context.actionability_reason else None,
        "failure_label": _failure_label(context) if context.category else None,
        "original_code": context.original_code,
        "proposed_selector": action.proposed_selector,
        "confidence": action.confidence,
        "reasoning": action.reasoning,
        "alternative_selectors": action.alternative_selectors,
        "raw_response": action.raw_response,
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