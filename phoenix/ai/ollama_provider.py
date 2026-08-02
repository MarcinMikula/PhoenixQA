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
from phoenix.ai.response_parser import parse_healing_response
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from config.settings import Settings

logger = logging.getLogger(__name__)


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
        """Returns (system_prompt, user_prompt) for context.category —
        see module docstring for which pair each category maps to."""
        if context.category == FailureCategory.LOCATOR_RESOLUTION:
            return SELECTOR_SYSTEM_PROMPT, build_selector_user_prompt(context)

        if (
            context.category == FailureCategory.ACTIONABILITY
            and context.actionability_reason == ActionabilityReason.RECEIVES_EVENTS
        ):
            return ACTIONABILITY_SYSTEM_PROMPT, build_actionability_user_prompt(context)

        raise NotImplementedError(
            f"OllamaProvider has no prompt for category={context.category}, "
            f"actionability_reason={context.actionability_reason} — "
            f"ContextCollector should not have produced a HealingContext "
            f"for this combination yet."
        )

    def _parse_response(self, context: HealingContext, raw_content: str):
        """Returns a HealingAction parsed with the same category-specific
        parser _build_prompt() used to build the prompt — kept as one
        pair per category so the two never drift apart independently."""
        if context.category == FailureCategory.LOCATOR_RESOLUTION:
            return parse_healing_response(raw_content)

        if (
            context.category == FailureCategory.ACTIONABILITY
            and context.actionability_reason == ActionabilityReason.RECEIVES_EVENTS
        ):
            strategy = parse_actionability_response(raw_content)
            # The model's own JSON never states which ActionabilityReason
            # it was answering for — that's context we already know from
            # the classifier, not something to re-derive from free-form
            # model output. Filled in here, not by the parser itself (see
            # actionability_response_parser.py's docstring on this field).
            strategy.reason = context.actionability_reason
            # DEBUG-only visibility into the parsed proposal itself, not
            # just that a round-trip happened — added specifically to
            # inspect real model output quality before any decision about
            # executing an ActionabilityStrategy (see LEARNINGS.md
            # "Sprint 6B — live ActionabilityStrategy proposal
            # inspection"). Mirrors the existing symmetric debug logging
            # for the selector path's HTTP round-trip above — same risk
            # profile (DEBUG level, opt-in via --log-cli-level=DEBUG,
            # nothing printed by default), so kept as a permanent log
            # line rather than temporary throwaway code, not gated behind
            # a separate env flag.
            logger.debug(
                f"[Ollama] Parsed ActionabilityStrategy: strategy={strategy.strategy.value}, "
                f"confidence={strategy.confidence:.2f}, "
                f"suggested_wait_ms={strategy.suggested_wait_ms}, "
                f"blocking_element={strategy.blocking_element!r}, "
                f"reasoning={strategy.reasoning!r}"
            )
            return strategy

        raise NotImplementedError(
            f"OllamaProvider has no parser for category={context.category}, "
            f"actionability_reason={context.actionability_reason}."
        )

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