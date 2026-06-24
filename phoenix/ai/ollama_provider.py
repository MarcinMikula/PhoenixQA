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
"""
import logging

import httpx

from phoenix.ai.base_provider import BaseProvider, HealingContext, HealingProposal
from phoenix.ai.prompt_templates import SYSTEM_PROMPT, build_user_prompt
from phoenix.ai.response_parser import parse_healing_response
from config.settings import Settings

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model

    def analyze_failure(self, context: HealingContext) -> HealingProposal:
        """
        Sprint 3 scope: only called for FailureType.SELECTOR_NOT_FOUND —
        ContextCollector (Sprint 2) doesn't produce a HealingContext for
        any other failure type yet, so this never has to branch on
        failure_type itself. That branching point lives in Healer
        (Sprint 4/5) once other failure types have real prompts to use.
        """
        user_prompt = build_user_prompt(context)

        logger.debug(
            f"[Ollama] Sending healing prompt ({len(user_prompt)} chars) to {self.model}"
        )

        payload = {
            "model": self.model,
            "prompt": user_prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
        }

        response = httpx.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_content = data.get("response", "")

        logger.debug(f"[Ollama] Response received ({len(raw_content)} chars)")

        return parse_healing_response(raw_content)

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
