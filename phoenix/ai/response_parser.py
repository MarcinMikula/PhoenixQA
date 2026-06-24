"""
response_parser.py

Parses raw LLM text output into a HealingProposal. Kept separate from the
HTTP/provider plumbing so parsing logic can be tested and hardened
independently — this is the piece most likely to need iteration as we see
real model output (see LEARNINGS.md Sprint 3 model selection note: even
llama3.2 isn't guaranteed to return clean JSON every time).

Defensive by design:
- strips markdown code fences (```json ... ``` or ``` ... ```) if present
- extracts the first {...} block if there's stray text before/after
- falls back to a zero-confidence proposal (never crashes the pipeline)
  if parsing fails entirely — a malformed response should look like
  "the model wasn't confident," not like a Python exception in Sprint 4/5
"""
import json
import re

from phoenix.ai.base_provider import HealingProposal

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_healing_response(raw_response: str) -> HealingProposal:
    """
    Best-effort parse of raw LLM text into a HealingProposal.
    Never raises — a response that can't be parsed becomes a
    zero-confidence proposal instead, so Safe Mode (Sprint 4) can
    legitimately reject it via the normal confidence-threshold path
    rather than the whole pipeline crashing on a bad LLM response.
    """
    json_text = _extract_json_text(raw_response)

    if json_text is None:
        return _fallback_proposal(raw_response, reason="No JSON object found in response")

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        return _fallback_proposal(raw_response, reason=f"JSON parse error: {e}")

    proposed_selector = data.get("proposed_selector")
    if not proposed_selector or not isinstance(proposed_selector, str):
        return _fallback_proposal(raw_response, reason="Missing or invalid 'proposed_selector' field")

    confidence = data.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))  # clamp to valid range

    reasoning = data.get("reasoning", "")
    alternatives = data.get("alternative_selectors", [])
    if not isinstance(alternatives, list):
        alternatives = []

    return HealingProposal(
        proposed_selector=proposed_selector,
        confidence=confidence,
        reasoning=str(reasoning),
        alternative_selectors=[str(a) for a in alternatives],
        raw_response=raw_response,
    )


def _extract_json_text(raw_response: str):
    """
    Tries, in order: markdown code fence content, a bare {...} block
    anywhere in the text, then — if neither matches a complete object —
    everything from the first '{' onward. That last fallback exists so a
    truncated response (model cut off mid-generation) still reaches
    json.loads() and produces a real "JSON parse error" message, instead
    of being misreported as "no JSON object found" when a '{' clearly
    was present, just never closed.
    """
    fence_match = _CODE_FENCE_RE.search(raw_response)
    if fence_match:
        return fence_match.group(1).strip()

    object_match = _JSON_OBJECT_RE.search(raw_response)
    if object_match:
        return object_match.group(0)

    brace_index = raw_response.find("{")
    if brace_index != -1:
        return raw_response[brace_index:]

    return None


def _fallback_proposal(raw_response: str, reason: str) -> HealingProposal:
    """
    A parse failure is real information, not a crash — surfaced as a
    zero-confidence proposal so downstream Safe/Autonomous Mode logic
    (Sprint 4/5) can treat it the same way as "model wasn't sure,"
    which is honestly what it usually means in practice.
    """
    return HealingProposal(
        proposed_selector="",
        confidence=0.0,
        reasoning=f"Failed to parse LLM response: {reason}",
        alternative_selectors=[],
        raw_response=raw_response,
    )
