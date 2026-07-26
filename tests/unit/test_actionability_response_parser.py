"""
test_actionability_response_parser.py

Unit tests for parse_actionability_response — the ACTIONABILITY /
RECEIVES_EVENTS counterpart to test_response_parser.py. Same defensive-
parsing coverage (clean JSON, fenced JSON, stray text, truncated JSON,
missing/invalid fields, confidence clamping/coercion), adapted to
ActionabilityStrategy's shape: a strategy enum instead of a selector
string, plus the nullable suggested_wait_ms/blocking_element fields.
No live LLM needed — pure string parsing logic.
"""
import pytest

from phoenix.ai.actionability_response_parser import parse_actionability_response
from phoenix.healing.actions import ActionabilityStrategyKind


@pytest.mark.unit
class TestParseActionabilityResponse:
    def test_clean_json_dismiss_blocker_parses_correctly(self):
        raw = """{
            "strategy": "dismiss_blocker",
            "confidence": 0.82,
            "reasoning": "A full-viewport overlay with pointer-events enabled sits above the target.",
            "suggested_wait_ms": null,
            "blocking_element": "<div data-testid=\\"chaos-pointer-events-overlay\\"></div>"
        }"""
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.DISMISS_BLOCKER
        assert result.confidence == 0.82
        assert "overlay" in result.reasoning
        assert result.suggested_wait_ms is None
        assert "chaos-pointer-events-overlay" in result.blocking_element

    def test_clean_json_wait_and_retry_parses_correctly(self):
        raw = """{
            "strategy": "wait_and_retry",
            "confidence": 0.7,
            "reasoning": "The blocker looks like a transient loading spinner.",
            "suggested_wait_ms": 800,
            "blocking_element": null
        }"""
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY
        assert result.suggested_wait_ms == 800
        assert result.blocking_element is None

    def test_no_safe_recovery_is_a_legitimate_response_not_just_a_fallback(self):
        raw = """{"strategy": "no_safe_recovery", "confidence": 0.2, "reasoning": "Cannot tell what the blocker is or how to resolve it.", "suggested_wait_ms": null, "blocking_element": null}"""
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert result.confidence == 0.2

    def test_json_wrapped_in_markdown_code_fence(self):
        raw = """Here is my analysis:
```json
{
    "strategy": "dismiss_blocker",
    "confidence": 0.75,
    "reasoning": "Cookie consent banner is covering the button.",
    "suggested_wait_ms": null,
    "blocking_element": "<div class=\\"cookie-banner\\"></div>"
}
```
Hope that helps!"""
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.DISMISS_BLOCKER
        assert result.confidence == 0.75

    def test_stray_text_before_and_after_json_object(self):
        raw = """Sure, here's my recommendation: {"strategy": "wait_and_retry", "confidence": 0.6, "reasoning": "ok", "suggested_wait_ms": 500, "blocking_element": null} Let me know if you need anything else."""
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.WAIT_AND_RETRY

    def test_completely_unparseable_response_falls_back_to_no_safe_recovery(self):
        raw = "I'm not sure what's blocking this element."
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert result.confidence == 0.0
        assert "Failed to parse" in result.reasoning
        assert result.raw_response == raw

    def test_malformed_json_falls_back_to_no_safe_recovery(self):
        raw = '{"strategy": "dismiss_blocker", "confidence": 0.7,'  # truncated
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert "JSON parse error" in result.reasoning

    def test_missing_strategy_field_falls_back(self):
        raw = '{"confidence": 0.9, "reasoning": "no strategy given"}'
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert "Missing or unrecognized" in result.reasoning

    def test_hallucinated_strategy_value_falls_back_rather_than_crashing(self):
        # A model inventing a strategy name that isn't in
        # ActionabilityStrategyKind (typo, or a value from a different
        # prompt entirely) must not raise ValueError from the Enum
        # constructor — same "malformed input becomes low confidence,
        # never a crash" principle as response_parser.py.
        raw = '{"strategy": "close_the_popup", "confidence": 0.8, "reasoning": "ok"}'
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.NO_SAFE_RECOVERY
        assert "close_the_popup" in result.reasoning

    def test_force_not_allowed_is_parsed_not_rejected(self):
        # The system prompt instructs the model never to propose this,
        # but the parser's job is to honestly reflect what the model
        # said, not to enforce that instruction — see module docstring.
        # Nothing currently acts on ActionabilityStrategy at all (Healer
        # rejects every instance regardless of strategy), so there is no
        # live enforcement point for the parser to bypass.
        raw = '{"strategy": "force_not_allowed", "confidence": 0.9, "reasoning": "forcing anyway"}'
        result = parse_actionability_response(raw)
        assert result.strategy == ActionabilityStrategyKind.FORCE_NOT_ALLOWED

    def test_confidence_out_of_range_gets_clamped(self):
        raw = '{"strategy": "wait_and_retry", "confidence": 1.7, "reasoning": "overconfident", "suggested_wait_ms": 300}'
        result = parse_actionability_response(raw)
        assert result.confidence == 1.0

    def test_confidence_as_string_is_coerced(self):
        raw = '{"strategy": "wait_and_retry", "confidence": "0.55", "reasoning": "ok", "suggested_wait_ms": 300}'
        result = parse_actionability_response(raw)
        assert result.confidence == 0.55

    def test_suggested_wait_ms_as_string_is_coerced(self):
        raw = '{"strategy": "wait_and_retry", "confidence": 0.6, "reasoning": "ok", "suggested_wait_ms": "750"}'
        result = parse_actionability_response(raw)
        assert result.suggested_wait_ms == 750

    def test_suggested_wait_ms_invalid_value_becomes_none_not_a_crash(self):
        raw = '{"strategy": "wait_and_retry", "confidence": 0.6, "reasoning": "ok", "suggested_wait_ms": "soon"}'
        result = parse_actionability_response(raw)
        assert result.suggested_wait_ms is None

    def test_blocking_element_non_string_is_coerced_not_crashed_on(self):
        raw = '{"strategy": "dismiss_blocker", "confidence": 0.6, "reasoning": "ok", "blocking_element": 12345}'
        result = parse_actionability_response(raw)
        assert result.blocking_element == "12345"

    def test_reason_field_is_not_set_by_the_parser(self):
        # ActionabilityStrategy.reason is filled in by the caller from
        # HealingContext.actionability_reason (already known from the
        # classifier), not re-derived from the model's own JSON — see
        # module docstring. The parser must leave it None.
        raw = '{"strategy": "wait_and_retry", "confidence": 0.6, "reasoning": "ok", "suggested_wait_ms": 300}'
        result = parse_actionability_response(raw)
        assert result.reason is None