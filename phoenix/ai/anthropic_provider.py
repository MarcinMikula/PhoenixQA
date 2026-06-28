"""
anthropic_provider.py
Claude (Anthropic API) — best quality healing suggestions.
TODO: implement prompt engineering + JSON parsing. Not yet built —
OllamaProvider was the priority for local, no-cost iteration during
Sprint 3-5 development.
"""
from phoenix.ai.base_provider import BaseProvider, HealingContext, ProviderResult
from config.settings import Settings


class AnthropicProvider(BaseProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze_failure(self, context: HealingContext) -> ProviderResult:
        raise NotImplementedError("AnthropicProvider — not yet implemented")

    def health_check(self) -> bool:
        raise NotImplementedError("AnthropicProvider — not yet implemented")
