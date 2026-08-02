"""
test_ollama_provider.py

First unit tests for OllamaProvider. Previously untested at the unit
level — Sprint 4/5 verification for the LOCATOR_RESOLUTION path was done
via live end-to-end runs only (see LEARNINGS.md). Added now because the
Sprint 6B actionability provider path needs to prove something a live
run alone can't cheaply prove on every commit: that analyze_failure()
routes to the RIGHT prompt/parser pair for the RIGHT category, and
raises loudly rather than silently reusing the selector path for an
actionability context (or vice versa).

httpx.get (health_check) and httpx.post (the actual /api/generate call)
are both mocked — no live Ollama needed. The LOCATOR_RESOLUTION test
is a regression check confirming existing Sprint 3-5 behavior is
unchanged by this slice's branching refactor, not new coverage on its
own.
"""
from unittest.mock import MagicMock

import pytest

from phoenix.ai.ollama_provider import OllamaProvider
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.ai.base_provider import HealingContext
from phoenix.healing.actions import ActionabilityStrategy, SelectorReplacement
from config.settings import Settings


def _make_settings():
    settings = MagicMock(spec=Settings)
    settings.ollama_base_url = "http://localhost:11434"
    settings.ollama_model = "llama3.2"
    return settings


def _make_locator_resolution_context():
    return HealingContext(
        broken_selector="[data-testid='username']",
        error_message="Locator.fill: Timeout 30000ms exceeded.",
        dom_snapshot="<input data-testid='username-x7f2'>",
        page_url="http://localhost:5173/",
        original_code="fill",
        category=FailureCategory.LOCATOR_RESOLUTION,
    )


def _make_receives_events_context():
    return HealingContext(
        broken_selector="[data-testid='btn-login']",
        error_message="Locator.click: intercepts pointer events",
        dom_snapshot="Target element:\n<button data-testid='btn-login'>",
        page_url="http://localhost:5173/",
        original_code="click",
        category=FailureCategory.ACTIONABILITY,
        actionability_reason=ActionabilityReason.RECEIVES_EVENTS,
        collector_metadata={
            "blocking_element_from_call_log": "<div data-testid='chaos-pointer-events-overlay'>",
            "target_outer_html": "<button data-testid='btn-login'>Log in</button>",
            "target_bounding_box": {"x": 10, "y": 20, "width": 80, "height": 30},
            "blocking_element_outer_html": "<div data-testid='chaos-pointer-events-overlay'></div>",
            "blocking_element_bounding_box": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "blocking_element_computed_style": {
                "position": "fixed", "zIndex": "9999", "pointerEvents": "auto",
                "opacity": "1", "display": "block", "visibility": "visible",
            },
        },
    )


def _mock_ollama_http(monkeypatch, raw_response_text: str, prompt_eval_count=800, eval_count=120):
    """Mocks both the health-check GET and the /api/generate POST so no
    real network call happens. Returns the mock for post so a test can
    assert on what payload was actually sent."""
    health_response = MagicMock()
    health_response.raise_for_status.return_value = None
    health_response.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
    monkeypatch.setattr("httpx.get", MagicMock(return_value=health_response))

    generate_response = MagicMock()
    generate_response.raise_for_status.return_value = None
    generate_response.json.return_value = {
        "response": raw_response_text,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }
    post_mock = MagicMock(return_value=generate_response)
    monkeypatch.setattr("httpx.post", post_mock)
    return post_mock


@pytest.mark.unit
class TestOllamaProviderLocatorResolution:
    def test_uses_selector_prompt_and_parser_unchanged(self, monkeypatch):
        raw = '{"proposed_selector": "[data-testid=\\"username-gffw\\"]", "confidence": 0.95, "reasoning": "matches base name", "alternative_selectors": []}'
        post_mock = _mock_ollama_http(monkeypatch, raw)

        provider = OllamaProvider(_make_settings())
        result = provider.analyze_failure(_make_locator_resolution_context())

        assert isinstance(result.action, SelectorReplacement)
        assert result.action.proposed_selector == "[data-testid=\"username-gffw\"]"
        assert result.input_tokens == 800
        assert result.output_tokens == 120

        # Confirm the selector system prompt was sent, not the actionability one.
        sent_payload = post_mock.call_args.kwargs["json"]
        assert "propose the replacement selector" in sent_payload["system"].lower() or \
               "css selector" in sent_payload["system"].lower()


@pytest.mark.unit
class TestOllamaProviderReceivesEvents:
    def test_uses_actionability_prompt_and_parser(self, monkeypatch):
        raw = (
            '{"strategy": "dismiss_blocker", "confidence": 0.82, '
            '"reasoning": "Full-viewport overlay above target.", '
            '"suggested_wait_ms": null, '
            '"blocking_element": "<div data-testid=\\"chaos-pointer-events-overlay\\"></div>"}'
        )
        post_mock = _mock_ollama_http(monkeypatch, raw)

        provider = OllamaProvider(_make_settings())
        result = provider.analyze_failure(_make_receives_events_context())

        assert isinstance(result.action, ActionabilityStrategy)
        assert result.action.strategy.value == "dismiss_blocker"
        assert result.action.confidence == 0.82
        # reason is filled in by the provider from the context, not the
        # model's own JSON — see actionability_response_parser.py.
        assert result.action.reason == ActionabilityReason.RECEIVES_EVENTS

        sent_payload = post_mock.call_args.kwargs["json"]
        assert "recovery strategy" in sent_payload["system"].lower()
        # The target element's own HTML must reach the prompt — this is
        # the whole point of reading collector_metadata instead of
        # dom_snapshot.
        assert "btn-login" in sent_payload["prompt"]

    def test_parsed_strategy_is_logged_at_debug_level(self, monkeypatch, caplog):
        # Added specifically to inspect real model output quality before
        # any Option-B execution decision — see LEARNINGS.md "Sprint 6B
        # — live ActionabilityStrategy proposal inspection". Protects
        # the log line itself, not just that parsing succeeds.
        raw = (
            '{"strategy": "dismiss_blocker", "confidence": 0.82, '
            '"reasoning": "Full-viewport overlay above target.", '
            '"suggested_wait_ms": null, '
            '"blocking_element": "<div data-testid=\\"chaos-pointer-events-overlay\\"></div>"}'
        )
        _mock_ollama_http(monkeypatch, raw)

        provider = OllamaProvider(_make_settings())
        with caplog.at_level("DEBUG", logger="phoenix.ai.ollama_provider"):
            provider.analyze_failure(_make_receives_events_context())

        debug_messages = [r.message for r in caplog.records]
        matching = [m for m in debug_messages if "Parsed ActionabilityStrategy" in m]
        assert len(matching) == 1
        assert "strategy=dismiss_blocker" in matching[0]
        assert "confidence=0.82" in matching[0]

    def test_malformed_response_still_returns_a_typed_result_not_a_crash(self, monkeypatch):
        _mock_ollama_http(monkeypatch, "not valid json at all")

        provider = OllamaProvider(_make_settings())
        result = provider.analyze_failure(_make_receives_events_context())

        assert isinstance(result.action, ActionabilityStrategy)
        assert result.action.confidence == 0.0
        assert result.action.strategy.value == "no_safe_recovery"


@pytest.mark.unit
class TestOllamaProviderUnsupportedCombination:
    def test_raises_before_any_network_call_for_unrecognized_category(self, monkeypatch):
        # A category/reason combination ContextCollector should never
        # actually produce today (see ActionabilityCollector, which
        # raises NotImplementedError upstream for anything but
        # RECEIVES_EVENTS) — this guards the provider itself rather than
        # trusting that invariant to hold forever upstream.
        post_mock = MagicMock()
        monkeypatch.setattr("httpx.post", post_mock)
        get_mock = MagicMock()
        monkeypatch.setattr("httpx.get", get_mock)

        context = HealingContext(
            broken_selector="[data-testid='x']",
            error_message="some error",
            dom_snapshot="",
            page_url="http://localhost:5173/",
            original_code="click",
            category=FailureCategory.ACTIONABILITY,
            actionability_reason=ActionabilityReason.STABLE,
        )

        provider = OllamaProvider(_make_settings())
        with pytest.raises(NotImplementedError, match="no prompt for"):
            provider.analyze_failure(context)

        get_mock.assert_not_called()
        post_mock.assert_not_called()