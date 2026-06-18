"""
test_provider_factory.py
Unit tests for AI provider factory.
"""
import pytest
from unittest.mock import patch
from phoenix.ai.provider_factory import get_provider
from phoenix.ai.anthropic_provider import AnthropicProvider
from phoenix.ai.ollama_provider import OllamaProvider
from config.settings import Settings


@pytest.mark.unit
class TestProviderFactory:
    def test_returns_ollama_provider(self):
        with patch.object(Settings, "ai_provider", "ollama"):
            provider = get_provider(Settings())
        assert isinstance(provider, OllamaProvider)

    def test_returns_anthropic_provider(self):
        with patch.object(Settings, "ai_provider", "anthropic"):
            provider = get_provider(Settings())
        assert isinstance(provider, AnthropicProvider)

    def test_raises_on_unknown_provider(self):
        with patch.object(Settings, "ai_provider", "gpt-unknown"):
            with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
                get_provider(Settings())
