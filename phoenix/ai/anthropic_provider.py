"""
anthropic_provider.py
Claude (Anthropic API) — best quality healing suggestions.
TODO Sprint 3: implement prompt engineering + JSON parsing.
"""
from phoenix.ai.base_provider import BaseProvider, HealingContext, HealingProposal
from config.settings import Settings


class AnthropicProvider(BaseProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze_failure(self, context: HealingContext) -> HealingProposal:
        raise NotImplementedError("AnthropicProvider — implement in Sprint 3")

    def health_check(self) -> bool:
        raise NotImplementedError("AnthropicProvider — implement in Sprint 3")
