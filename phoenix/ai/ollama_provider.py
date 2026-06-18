"""
ollama_provider.py
Local LLM via Ollama — air-gapped / NDA-safe. No data leaves the machine.
TODO Sprint 3: implement prompt engineering + JSON parsing.
"""
from phoenix.ai.base_provider import BaseProvider, HealingContext, HealingProposal
from config.settings import Settings


class OllamaProvider(BaseProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    def analyze_failure(self, context: HealingContext) -> HealingProposal:
        raise NotImplementedError("OllamaProvider — implement in Sprint 3")

    def health_check(self) -> bool:
        raise NotImplementedError("OllamaProvider — implement in Sprint 3")
