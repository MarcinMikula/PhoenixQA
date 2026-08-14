"""
ollama_provider.py
Local LLM via Ollama — air-gapped / NDA-safe. No data leaves the machine.

Convention mirrors defect-pilot's ai/ollama_provider.py (httpx, /api/generate,
stream: False, is_available() health check via /api/tags) — confirmed by
reading the actual file rather than guessing the shape.

Sprint 3 default model: llama3.2 (text-optimized), not llava. See
LEARNINGS.md "Sprint 3 — Decision: separate model for Sprint 3
verification" for why llava (vision-first, older text architecture) was
deliberately set aside for this sprint rather than fighting two unknowns
(prompt architecture + model JSON-reliability) at once.

Sprint 6B (decision): analyze_failure() returns ProviderResult.action
(a HealingAction, today always a SelectorReplacement), not the old
ProviderResult.proposal — see phoenix/healing/actions.py.

Sprint 6B (implementation, actionability provider path): analyze_failure()
now branches on context.category. FailureCategory.LOCATOR_RESOLUTION uses
the existing selector prompt/parser (phoenix/ai/prompt_templates.py +
phoenix/ai/response_parser.py), unchanged. FailureCategory.ACTIONABILITY
with ActionabilityReason.RECEIVES_EVENTS uses the new
phoenix/ai/prompts/actionability_prompt.py +
phoenix/ai/actionability_response_parser.py pair. Any other
category/reason combination reaching this method would mean
ContextCollector produced a HealingContext for something it has no
collector for yet — that should be structurally impossible today (see
ActionabilityCollector, which raises NotImplementedError for the other
four ActionabilityReason values before a HealingContext ever gets
built), but this method still guards explicitly rather than silently
falling through to the selector path on an unrecognized category.

Sprint 6B (reproducibility): analyze_failure() pins both `temperature`
and `seed` in the request's `options` — Ollama's own default temperature
(0.8 for llama3.2, per Ollama's documented runtime options) was
previously left unset entirely. Directly implicated as the cause of a
real observed problem, not a precaution: four live RECEIVES_EVENTS runs
against an IDENTICAL prompt returned three different confidence values
and two different strategies (3x wait_and_retry, 1x dismiss_blocker) —
see LEARNINGS.md "Sprint 6B — three more live samples, same scenario."
Pinning `temperature=0` alone reduces (but per Ollama's own docs does
not strictly guarantee, since GPU floating-point non-associativity can
still introduce drift) run-to-run variance; adding a fixed `seed`
addresses the same non-determinism from the sampling side. Together they
let a future re-run separate two genuinely different diagnoses — "the
model unreliably samples between good and bad answers" vs. "the model
reliably produces the same, possibly wrong, answer" — which requires
knowing sampling is no longer the variable in play.

Sprint 6B (policy guardrail): even with temperature/seed pinned and a
revised prompt (explicit self-consistency instruction, corrected
few-shot examples), llama3.2 still deterministically proposed
wait_and_retry for a blocker it had itself correctly described, in the
same response, as persistent with no dismiss affordance — see
LEARNINGS.md "actionability_prompt.py revised" and its live-verification
follow-up. Prompt engineering alone was not sufficient. _parse_response()
now runs every RECEIVES_EVENTS proposal through
phoenix/healing/actionability_policy.py before returning it — a
deterministic check against collector_metadata (not the model's
reasoning text) that can override an unsafe wait_and_retry proposal.
The model proposes; this policy validates. See that module's docstring
for the full reasoning.

Sprint 6B (second ActionabilityReason): ActionabilityReason.VISIBLE
added alongside RECEIVES_EVENTS, using its own reason-specific prompt
(phoenix/ai/prompts/visible_prompt.py) and its own policy entry point
(actionability_policy.validate_visible_strategy) — but the SAME
response parser (actionability_response_parser.py is reason-agnostic:
its JSON shape doesn't vary by reason) and the SAME debug-log +
policy-correction pattern, now factored into
_run_actionability_policy() so both reasons share it rather than
duplicating the same three lines of logging twice.
"""
import logging
import time

import httpx

from phoenix.ai.actionability_response_parser import parse_actionability_response
from phoenix.ai.base_provider import BaseProvider, HealingContext, ProviderResult
from phoenix.ai.prompt_templates import SYSTEM_PROMPT as SELECTOR_SYSTEM_PROMPT
from phoenix.ai.prompt_templates import build_user_prompt as build_selector_user_prompt
from phoenix.ai.prompts.actionability_prompt import SYSTEM_PROMPT as ACTIONABILITY_SYSTEM_PROMPT
from phoenix.ai.prompts.actionability_prompt import build_user_prompt as build_actionability_user_prompt
from phoenix.ai.prompts.visible_prompt import SYSTEM_PROMPT as VISIBLE_SYSTEM_PROMPT
from phoenix.ai.prompts.visible_prompt import build_user_prompt as build_visible_user_prompt
from phoenix.ai.response_parser import parse_healing_response
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.actionability_policy import (
    validate_receives_events_strategy,
    validate_visible_strategy,
)
from config.settings import Settings

logger = logging.getLogger(__name__)

# Sprint 6B — see module docstring "Sprint 6B (reproducibility)" for the
# full rationale. Applied to EVERY OllamaProvider call (both
# LOCATOR_RESOLUTION and ACTIONABILITY paths share this one payload
# construction) — reproducibility is a general provider-quality
# property, not something specific to the actionability investigation
# that surfaced the need for it. 42 has no special meaning beyond being
# a fixed, memorable constant — any fixed value produces the same
# reproducibility property.
OLLAMA_TEMPERATURE = 0
OLLAMA_SEED = 42


class OllamaProvider(BaseProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model

    def analyze_failure(self, context: HealingContext) -> ProviderResult:
        """
        Sprint 5: returns ProviderResult, not a bare HealingAction —
        HealingBudget needs the token/timing metadata to enforce limits.
        elapsed_ms measures the full HTTP round-trip, not just the
        model's own reported timing, since that's what actually counts
        against a wall-clock budget.

        Prompt/parser selection is branched by category (see module
        docstring); the HTTP round-trip and token/timing bookkeeping
        below are shared and unaware of which one was used.
        """
        system_prompt, user_prompt = self._build_prompt(context)

        # Caught via a real end-to-end run: calling /api/generate with a
        # model that isn't pulled returns a bare 404 from Ollama, which
        # surfaces as a generic httpx.HTTPStatusError with no indication
        # of WHY. health_check() already knows how to give a clear,
        # actionable message ("Run: ollama pull X") — running it first
        # turns a confusing 404 into an honest error before wasting a
        # round-trip on a request that can't succeed.
        if not self.health_check():
            raise RuntimeError(
                f"Ollama model '{self.model}' is not available. "
                f"Run: ollama pull {self.model}"
            )

        logger.debug(
            f"[Ollama] Sending healing prompt ({len(user_prompt)} chars) to {self.model}"
        )

        payload = {
            "model": self.model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": OLLAMA_TEMPERATURE,
                "seed": OLLAMA_SEED,
            },
        }

        start = time.monotonic()
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=120.0,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        response.raise_for_status()
        data = response.json()
        raw_content = data.get("response", "")

        logger.debug(
            f"[Ollama] Response received ({len(raw_content)} chars) in {elapsed_ms}ms"
        )

        action = self._parse_response(context, raw_content)

        # Ollama's /api/generate reports prompt_eval_count (input) and
        # eval_count (output) when available — not guaranteed on every
        # response shape, hence .get() with no default rather than
        # assuming the keys exist.
        return ProviderResult(
            action=action,
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            elapsed_ms=elapsed_ms,
        )

    def _build_prompt(self, context: HealingContext) -> tuple:
        """Returns (system_prompt, user_prompt) for context.category
        (and, for ACTIONABILITY, context.actionability_reason) — see
        module docstring for which pair each maps to."""
        if context.category == FailureCategory.LOCATOR_RESOLUTION:
            return SELECTOR_SYSTEM_PROMPT, build_selector_user_prompt(context)

        if context.category == FailureCategory.ACTIONABILITY:
            if context.actionability_reason == ActionabilityReason.RECEIVES_EVENTS:
                return ACTIONABILITY_SYSTEM_PROMPT, build_actionability_user_prompt(context)
            if context.actionability_reason == ActionabilityReason.VISIBLE:
                return VISIBLE_SYSTEM_PROMPT, build_visible_user_prompt(context)

        raise NotImplementedError(
            f"OllamaProvider has no prompt for category={context.category}, "
            f"actionability_reason={context.actionability_reason} — "
            f"ContextCollector should not have produced a HealingContext "
            f"for this combination yet."
        )

    def _parse_response(self, context: HealingContext, raw_content: str):
        """Returns a HealingAction parsed with the same category-specific
        parser _build_prompt() used to build the prompt — kept as one
        pair per category/reason so the two never drift apart
        independently."""
        if context.category == FailureCategory.LOCATOR_RESOLUTION:
            return parse_healing_response(raw_content)

        if context.category == FailureCategory.ACTIONABILITY:
            if context.actionability_reason == ActionabilityReason.RECEIVES_EVENTS:
                return self._run_actionability_policy(
                    context, raw_content, validate_receives_events_strategy
                )
            if context.actionability_reason == ActionabilityReason.VISIBLE:
                return self._run_actionability_policy(
                    context, raw_content, validate_visible_strategy
                )

        raise NotImplementedError(
            f"OllamaProvider has no parser for category={context.category}, "
            f"actionability_reason={context.actionability_reason}."
        )

    def _run_actionability_policy(self, context: HealingContext, raw_content: str, policy_fn):
        """
        Shared by every ActionabilityReason with a real parser/policy
        pair (currently RECEIVES_EVENTS and VISIBLE — Sprint 6B). The
        response shape is reason-agnostic (parse_actionability_response()
        doesn't branch on reason at all), so only the POLICY function
        differs per reason — passed in explicitly by the caller rather
        than looked up by a dict keyed on reason, keeping each reason's
        wiring visible at its own call site in _parse_response() above.

        DEBUG-only visibility into the parsed proposal itself, not just
        that a round-trip happened — added specifically to inspect real
        model output quality before any decision about executing an
        ActionabilityStrategy (see LEARNINGS.md "Sprint 6B — live
        ActionabilityStrategy proposal inspection"). Mirrors the
        existing symmetric debug logging for the selector path's HTTP
        round-trip — same risk profile (DEBUG level, opt-in via
        --log-cli-level=DEBUG, nothing printed by default).

        The policy guardrail runs AFTER that debug log, not before, so
        the log line always shows exactly what the model proposed,
        unmodified — the policy layer's job is to decide whether that
        proposal is safe to act on, not to hide what was actually said.
        See actionability_policy.py's module docstring for why this
        exists and why it validates against collector_metadata rather
        than the model's reasoning text.
        """
        strategy = parse_actionability_response(raw_content)
        # The model's own JSON never states which ActionabilityReason it
        # was answering for — that's context we already know from the
        # classifier, not something to re-derive from free-form model
        # output. Filled in here, not by the parser itself (see
        # actionability_response_parser.py's docstring on this field).
        strategy.reason = context.actionability_reason

        logger.debug(
            f"[Ollama] Parsed ActionabilityStrategy: strategy={strategy.strategy.value}, "
            f"confidence={strategy.confidence:.2f}, "
            f"suggested_wait_ms={strategy.suggested_wait_ms}, "
            f"blocking_element={strategy.blocking_element!r}, "
            f"reasoning={strategy.reasoning!r}"
        )

        validated = policy_fn(strategy, context)
        if validated.corrected_by_policy:
            logger.info(
                f"[Ollama] Policy corrected ActionabilityStrategy: "
                f"{validated.original_strategy.value} -> {validated.strategy.value} "
                f"({validated.policy_reason})"
            )
        return validated

    def health_check(self) -> bool:
        """
        Verifies Ollama is reachable AND the configured model is actually
        pulled — mirrors defect-pilot's is_available(), which catches the
        common "Ollama is running but I forgot to `ollama pull` the model"
        mistake rather than failing later with a confusing 404.
        """
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            model_names = [m.split(":")[0] for m in models]
            if self.model.split(":")[0] not in model_names:
                logger.warning(
                    f"[Ollama] Model '{self.model}' not found. "
                    f"Available: {models}. Run: ollama pull {self.model}"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"[Ollama] Health check failed: {e}. Is Ollama running?")
            return False