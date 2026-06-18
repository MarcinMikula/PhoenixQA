"""
provider_factory.py
Returns correct LLM provider based on AI_PROVIDER env var.
Single place to add new providers in the future.
"""
from config.settings import Settings
from phoenix.ai.base_provider import BaseProvider


def get_provider(settings: Settings) -> BaseProvider:
    provider = settings.ai_provider.lower()

    if provider == "anthropic":
        from phoenix.ai.anthropic_provider import AnthropicProvider
        return AnthropicProvider(settings)
    elif provider == "ollama":
        from phoenix.ai.ollama_provider import OllamaProvider
        return OllamaProvider(settings)
    else:
        raise ValueError(
            f"Unknown AI_PROVIDER: '{provider}'. Supported: 'anthropic', 'ollama'"
        )
