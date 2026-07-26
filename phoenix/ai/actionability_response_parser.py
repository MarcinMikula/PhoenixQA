"""
actionability_response_parser.py

Parses raw LLM text output into an ActionabilityStrategy — the
FailureCategory.ACTIONABILITY / ActionabilityReason.RECEIVES_EVENTS
counterpart to response_parser.py's parse_healing_response(). Kept as a
SEPARATE module rather than a second branch inside response_parser.py:
that file's own docstring already says it "is, and has only ever been,
called from the FailureCategory.LOCATOR_RESOLUTION path" — bolting a
second, differently-shaped parse path onto it would break that
invariant rather than extend it. See LEARNINGS.md "Sprint 6B
(implementation) — actionability provider path".

Deliberately does NOT import response_parser.py's private JSON-extraction
helper, even though the logic (fenced code block → bare {...} block →
first '{' onward) is currently identical. The two response shapes are
different enough (five-value strategy enum + nullable fields here, vs.
proposed_selector + alternatives there) that a shared private helper
would create a coupling between two paths this project has deliberately
kept apart — see the module docstring in phoenix/ai/prompts/actionability_prompt.py
for the same reasoning applied to the prompt side.

Defensive by design, same three-part fallback chain as
response_parser.py for the same reason: even a well-designed prompt
does not guarantee clean JSON every time (see LEARNINGS.md Sprint 3
model selection note).
"""
import json
import re

from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_VALID_STRATEGIES = {kind.value for kind in ActionabilityStrategyKind}


def parse_actionability_response(raw_response: str) -> ActionabilityStrategy:
    """
    Best-effort parse of raw LLM text into an ActionabilityStrategy.
    Never raises — a response that can't be parsed, or that names a
    strategy value the model invented, becomes a zero-confidence
    NO_SAFE_RECOVERY strategy instead, matching the same principle
    response_parser.py's _fallback_proposal() established: a malformed
    response should look like "the model wasn't confident," not a
    Python exception in the middle of the healing pipeline.

    Deliberately does NOT reject "force_not_allowed" here even though
    the system prompt instructs the model never to propose it — this
    parser's job is to honestly reflect what the model actually said,
    not to enforce policy. Nothing currently acts on an
    ActionabilityStrategy at all (Healer rejects every instance of this
    type today, regardless of which strategy it names — see
    healer.py), so there is no live enforcement point to bypass yet;
    if the model disobeys the instruction, that is itself useful
    information for whoever reads the decision log.
    """
    json_text = _extract_json_text(raw_response)

    if json_text is None:
        return _fallback_strategy(raw_response, reason="No JSON object found in response")

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        return _fallback_strategy(raw_response, reason=f"JSON parse error: {e}")

    strategy_raw = data.get("strategy")
    if not strategy_raw or not isinstance(strategy_raw, str) or strategy_raw not in _VALID_STRATEGIES:
        return _fallback_strategy(
            raw_response,
            reason=f"Missing or unrecognized 'strategy' value: {strategy_raw!r}",
        )
    strategy = ActionabilityStrategyKind(strategy_raw)

    confidence = data.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))  # clamp to valid range

    reasoning = data.get("reasoning", "")

    suggested_wait_ms = data.get("suggested_wait_ms")
    if suggested_wait_ms is not None:
        try:
            suggested_wait_ms = int(suggested_wait_ms)
        except (TypeError, ValueError):
            suggested_wait_ms = None

    blocking_element = data.get("blocking_element")
    if blocking_element is not None and not isinstance(blocking_element, str):
        blocking_element = str(blocking_element)

    return ActionabilityStrategy(
        confidence=confidence,
        reasoning=str(reasoning),
        raw_response=raw_response,
        reason=None,  # filled in by the caller from HealingContext.actionability_reason, not from the model's own output
        strategy=strategy,
        suggested_wait_ms=suggested_wait_ms,
        blocking_element=blocking_element,
    )


def _extract_json_text(raw_response: str):
    """
    Same three-step fallback chain as response_parser.py's helper of the
    same shape (fenced code block, bare {...} block, first '{' onward
    for a truncated response) — see that module's docstring for why the
    third step exists. Intentionally duplicated, not imported; see this
    module's own docstring for why.
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


def _fallback_strategy(raw_response: str, reason: str) -> ActionabilityStrategy:
    """
    A parse failure becomes NO_SAFE_RECOVERY at zero confidence — the
    honest "I don't have a usable answer" state, same role
    response_parser.py's empty proposed_selector plays for the selector
    path. Downstream, nothing currently branches on this (Healer
    rejects every ActionabilityStrategy regardless), but the shape
    stays meaningful for whenever that changes.
    """
    return ActionabilityStrategy(
        confidence=0.0,
        reasoning=f"Failed to parse LLM response: {reason}",
        raw_response=raw_response,
        strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
    )