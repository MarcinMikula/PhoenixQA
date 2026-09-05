"""
heuristic_provider.py

Sprint 8 (Gap #9) — the FailureCategory.LOCATOR_RESOLUTION baseline.
NOT a user-facing AI_PROVIDER option (not wired into provider_factory.py)
— per LEARNINGS.md "HeuristicProvider is a control, not a product
feature," this exists to answer RH-1 (does an LLM outperform a cheap
deterministic heuristic?), not to give end users a third healing mode.
Instantiated directly by whatever comparison script Sprint 8 produces.

Implements BaseProvider like any real provider — same interface, so the
comparison script can swap this in for OllamaProvider with zero other
code changes — but analyze_failure() never makes a network call.

DESIGN — anchors on the PRESENT, not history (see LEARNINGS.md Sprint 2
Gap #9 clarification): tokenize the broken selector's base name (reusing
locator_resolution_collector.tokenize_selector() — same rotation-suffix
stripping logic the LLM path's own collector already relies on, not a
second implementation of the same idea), then look for the best-matching
attribute value already present in HealingContext.dom_snapshot (the
landmark HTML ContextCollector already narrowed down via its own
weighted DOM scoring — this provider does NOT re-query the live DOM;
LOCATOR_RESOLUTION is the only category it handles, matching the
original Gap #9 scope).

FUZZY MATCHING — uses difflib.SequenceMatcher, not python-Levenshtein.
LEARNINGS.md/docs/gaps.md describe this baseline as "fuzzy/Levenshtein
token matching"; difflib.SequenceMatcher.ratio() is stdlib, needs no new
dependency, and provides the same class of fuzzy-similarity signal
(a normalized edit-distance-like ratio) that a true Levenshtein
implementation would — swappable later without changing this file's
public shape if a real benchmark run shows it matters. A deliberate
substitution, not a silent shortcut.

SCOPE — matches the original Gap #9 design exactly: LOCATOR_RESOLUTION
only. FailureCategory.ACTIONABILITY has its own, separate zero/near-
zero-LLM baseline (PolicyOnlyProvider, planned) — see LEARNINGS.md
"Sprint 8 (pre-coding)" for why one universal HeuristicProvider covering
both categories was rejected as the wrong shape for ACTIONABILITY's
already-deterministic collector_metadata.
"""
import difflib
import re

from phoenix.ai.base_provider import BaseProvider, HealingContext, ProviderResult
from phoenix.collector.collectors.locator_resolution_collector import tokenize_selector
from phoenix.collector.failure_classifier import FailureCategory
from phoenix.healing.actions import SelectorReplacement
from config.settings import Settings

# Same five attribute sources ContextCollector's own weighted scoring
# uses (see locator_resolution_collector.SCORE_WEIGHTS) — deliberately
# NOT textContent. textContent isn't a regex-extractable "attr=value"
# pair the way the other five are, and dom_snapshot is already narrowed
# to a landmark containing the right candidate(s), so the marginal value
# of also matching against loose text is low for a baseline whose whole
# point is to be cheap and simple. Tracked as a known scope limitation,
# not an oversight — a real benchmark run would reveal if this matters.
_ATTR_WEIGHTS = {
    "data-testid": 5,
    "aria-label": 4,
    "name": 4,
    "placeholder": 3,
    "id": 2,
}
_MAX_WEIGHT = max(_ATTR_WEIGHTS.values())

# Below this SIMILARITY (not combined score) there's no real match worth
# proposing — same spirit as the LLM path's own "say so honestly with
# low confidence rather than guessing" rule (see prompt_templates.py's
# SYSTEM_PROMPT step 5), enforced here as a hard cutoff instead of an
# instruction, since there's no model to ask.
_MIN_SIMILARITY = 0.5

# A tiny nudge added to the ranking score (never to the returned
# confidence) so that among near-tied candidates, the more INTENTIONAL
# attribute source wins — mirrors why the collector's own scoring
# weights data-testid over textContent. Deliberately small: a
# LOW-weight attribute with a genuinely BETTER textual match must still
# win over a HIGH-weight attribute with a worse one. Getting this
# backwards (multiplying similarity by weight/_MAX_WEIGHT) was caught in
# testing — it let a low weight (e.g. id=2) mathematically disqualify
# even a PERFECT match, which defeats the point of a weight that's
# meant to break ties, not override match quality.
_TIE_BREAK_EPSILON = 0.001


def _extract_candidates(html: str) -> list:
    """
    Regex-scans a landmark HTML snippet for attr="value" pairs across
    the five weighted sources. Deliberately simple (no real HTML
    parser) — dom_snapshot is a small, already-narrowed fragment
    ContextCollector produced specifically to be cheap to scan, not
    arbitrary untrusted HTML.
    """
    candidates = []
    for attr in _ATTR_WEIGHTS:
        for match in re.finditer(rf'{re.escape(attr)}=["\']([^"\']+)["\']', html):
            candidates.append((attr, match.group(1)))
    return candidates


def _selector_for(attr: str, value: str) -> str:
    """Renders an (attribute, value) match back into a CSS selector
    string, matching the format Chaos App's own selectors use
    (see pages/chaos_login_page.py) — '#value' for id, '[attr=value]'
    otherwise."""
    if attr == "id":
        return f"#{value}"
    return f"[{attr}='{value}']"


class HeuristicProvider(BaseProvider):
    def __init__(self, settings: Settings = None):
        # Settings accepted for interface parity with real providers
        # (OllamaProvider/AnthropicProvider both take one) even though
        # nothing here is currently configurable — no base_url, no
        # model name, nothing to read from it yet.
        self.settings = settings

    def analyze_failure(self, context: HealingContext) -> ProviderResult:
        """
        Zero-LLM baseline for FailureCategory.LOCATOR_RESOLUTION.
        Raises NotImplementedError for anything else — same "guard
        explicitly, don't silently fall through" discipline
        OllamaProvider.analyze_failure() already applies (see that
        file's module docstring).
        """
        if context.category != FailureCategory.LOCATOR_RESOLUTION:
            raise NotImplementedError(
                f"HeuristicProvider has no baseline for category={context.category} "
                f"yet — LOCATOR_RESOLUTION only (see Gap #9 in docs/gaps.md). "
                f"ACTIONABILITY's baseline is PolicyOnlyProvider, a separate class."
            )

        broken_base = "-".join(tokenize_selector(context.broken_selector))
        candidates = _extract_candidates(context.dom_snapshot)

        best_attr, best_value, best_similarity, best_rank_score = None, None, 0.0, 0.0
        for attr, value in candidates:
            candidate_base = "-".join(tokenize_selector(value))
            similarity = difflib.SequenceMatcher(None, broken_base, candidate_base).ratio()
            rank_score = similarity + (_ATTR_WEIGHTS[attr] / _MAX_WEIGHT) * _TIE_BREAK_EPSILON
            if rank_score > best_rank_score:
                best_attr, best_value, best_similarity, best_rank_score = (
                    attr, value, similarity, rank_score
                )

        if best_similarity < _MIN_SIMILARITY:
            return ProviderResult(
                action=SelectorReplacement(
                    confidence=0.0,
                    reasoning=(
                        "No candidate attribute in the provided DOM snapshot "
                        f"scored above the {_MIN_SIMILARITY} similarity threshold "
                        f"against base name '{broken_base}'."
                    ),
                    proposed_selector="",
                    raw_response="",
                )
            )

        return ProviderResult(
            action=SelectorReplacement(
                confidence=round(best_similarity, 2),
                reasoning=(
                    f"Best fuzzy match: {best_attr}='{best_value}' "
                    f"(similarity {best_similarity:.2f} against "
                    f"base name '{broken_base}')."
                ),
                proposed_selector=_selector_for(best_attr, best_value),
                raw_response="",
            )
        )

    def health_check(self) -> bool:
        """Always available — no network dependency, no model to be
        missing. Present only for BaseProvider interface parity."""
        return True
