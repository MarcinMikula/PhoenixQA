"""
test_response_parser.py

Unit tests for parse_healing_response. This is the piece most likely to
need hardening as we see real model output — llama3.2 isn't guaranteed
to return clean JSON every time (see LEARNINGS.md Sprint 3 notes).
No live Ollama needed — pure string parsing logic.
"""
import pytest

from phoenix.ai.response_parser import parse_healing_response


@pytest.mark.unit
class TestParseHealingResponse:
    def test_clean_json_parses_correctly(self):
        raw = """{
            "proposed_selector": "[data-testid='username-x7f2']",
            "confidence": 0.92,
            "reasoning": "Same form position, matching data-testid prefix",
            "alternative_selectors": ["#chaos-username"]
        }"""
        result = parse_healing_response(raw)
        assert result.proposed_selector == "[data-testid='username-x7f2']"
        assert result.confidence == 0.92
        assert "data-testid" in result.reasoning
        assert result.alternative_selectors == ["#chaos-username"]

    def test_json_wrapped_in_markdown_code_fence(self):
        raw = """Here is my analysis:
```json
{
    "proposed_selector": "#chaos-username",
    "confidence": 0.8,
    "reasoning": "Stable id attribute on the input",
    "alternative_selectors": []
}
```
Hope that helps!"""
        result = parse_healing_response(raw)
        assert result.proposed_selector == "#chaos-username"
        assert result.confidence == 0.8

    def test_json_wrapped_in_plain_code_fence_no_language_tag(self):
        raw = """```
{"proposed_selector": "#x", "confidence": 0.5, "reasoning": "test", "alternative_selectors": []}
```"""
        result = parse_healing_response(raw)
        assert result.proposed_selector == "#x"

    def test_stray_text_before_and_after_json_object(self):
        raw = """Sure, here's the fix: {"proposed_selector": "#y", "confidence": 0.6, "reasoning": "ok", "alternative_selectors": []} Let me know if you need anything else."""
        result = parse_healing_response(raw)
        assert result.proposed_selector == "#y"

    def test_completely_unparseable_response_falls_back_gracefully(self):
        raw = "I'm not sure how to help with this selector issue."
        result = parse_healing_response(raw)
        assert result.confidence == 0.0
        assert result.proposed_selector == ""
        assert "Failed to parse" in result.reasoning
        # raw_response must be preserved for debugging, even on failure
        assert result.raw_response == raw

    def test_malformed_json_falls_back_gracefully(self):
        raw = '{"proposed_selector": "#z", "confidence": 0.7,'  # truncated
        result = parse_healing_response(raw)
        assert result.confidence == 0.0
        assert "JSON parse error" in result.reasoning

    def test_missing_proposed_selector_field_falls_back(self):
        raw = '{"confidence": 0.9, "reasoning": "no selector given", "alternative_selectors": []}'
        result = parse_healing_response(raw)
        assert result.confidence == 0.0
        assert "Missing or invalid" in result.reasoning

    def test_confidence_out_of_range_gets_clamped(self):
        raw = '{"proposed_selector": "#a", "confidence": 1.5, "reasoning": "overconfident", "alternative_selectors": []}'
        result = parse_healing_response(raw)
        assert result.confidence == 1.0

    def test_confidence_as_string_is_coerced(self):
        # Some models return "0.8" as a string instead of a float —
        # observed often enough in practice to guard against explicitly.
        raw = '{"proposed_selector": "#a", "confidence": "0.8", "reasoning": "ok", "alternative_selectors": []}'
        result = parse_healing_response(raw)
        assert result.confidence == 0.8

    def test_alternative_selectors_not_a_list_defaults_to_empty(self):
        raw = '{"proposed_selector": "#a", "confidence": 0.5, "reasoning": "ok", "alternative_selectors": "not-a-list"}'
        result = parse_healing_response(raw)
        assert result.alternative_selectors == []
