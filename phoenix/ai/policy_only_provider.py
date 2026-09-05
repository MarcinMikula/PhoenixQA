"""
policy_only_provider.py

Sprint 8 (Gap #9) — the FailureCategory.ACTIONABILITY / VISIBLE
baseline. NOT a user-facing AI_PROVIDER option (not wired into
provider_factory.py), same reasoning as heuristic_provider.py: this is
an experimental control for RH-1, not a third healing mode.

DESIGN — this is NOT a smaller/cheaper LLM. It's the promotion of an
existing GUARDRAIL to being the decision-maker itself. VISIBLE is the
one implemented ActionabilityReason where ActionabilityCollector's
own evidence (collector_metadata["target_state_changed_during_observation"],
an OBSERVED FACT from two real DOM snapshots — see
actionability_collector.py and actionability_policy.py's
validate_visible_strategy() docstrings) is strong enough to BE the
decision, not merely validate one. This provider applies exactly that
rule directly:

    state changed during observation   -> WAIT_AND_RETRY
    state unchanged during observation -> NO_SAFE_RECOVERY

This is the SAME rule validate_visible_strategy() already encodes as a
correction check — deliberately reusing the identical threshold and
metadata key, not a second, possibly-drifting reimplementation of the
same idea. If that rule ever changes, both places need updating; a
future refactor could have validate_visible_strategy() call a shared
helper this provider also calls, but that consolidation isn't done yet
— tracked as a small follow-up, not blocking this slice.

SCOPE — ACTIONABILITY / VISIBLE only, matching the narrow Sprint 8
baseline design (see LEARNINGS.md "Sprint 8 (pre-coding)"). Explicitly
NOT RECEIVES_EVENTS: its evidence is CSS-declaration-based (animation/
transition capability), not an observed fact the way VISIBLE's is — a
policy-only decision there would be testing something structurally
weaker, not a cleaner comparison. LOCATOR_RESOLUTION has its own,
separate baseline (HeuristicProvider) — a different category needs a
genuinely different baseline shape, not this class extended to cover it.
"""
from phoenix.ai.base_provider import BaseProvider, HealingContext, ProviderResult
from phoenix.collector.failure_classifier import ActionabilityReason, FailureCategory
from phoenix.healing.actions import ActionabilityStrategy, ActionabilityStrategyKind
from config.settings import Settings


class PolicyOnlyProvider(BaseProvider):
    def __init__(self, settings: Settings = None):
        # Accepted for interface parity with real providers — see
        # heuristic_provider.py's identical note. Nothing here reads it.
        self.settings = settings

    def analyze_failure(self, context: HealingContext) -> ProviderResult:
        """
        Zero-LLM baseline for FailureCategory.ACTIONABILITY /
        ActionabilityReason.VISIBLE only. Raises NotImplementedError for
        anything else — same explicit-guard discipline
        OllamaProvider.analyze_failure() and HeuristicProvider.analyze_failure()
        already apply, rather than silently assuming a category/reason
        this provider was never designed for.
        """
        if (
            context.category != FailureCategory.ACTIONABILITY
            or context.actionability_reason != ActionabilityReason.VISIBLE
        ):
            raise NotImplementedError(
                f"PolicyOnlyProvider has no baseline for category={context.category}, "
                f"actionability_reason={context.actionability_reason} — "
                f"ACTIONABILITY/VISIBLE only (see Gap #9 in docs/gaps.md). "
                f"LOCATOR_RESOLUTION's baseline is HeuristicProvider, a separate class."
            )

        metadata = context.collector_metadata or {}
        state_changed = metadata.get("target_state_changed_during_observation", False)

        if state_changed:
            return ProviderResult(
                action=ActionabilityStrategy(
                    confidence=1.0,
                    reasoning=(
                        "collector_metadata reports the target's observed state "
                        "changed during the collection window — direct evidence "
                        "waiting longer may resolve the actionability failure."
                    ),
                    raw_response="",
                    reason=ActionabilityReason.VISIBLE,
                    strategy=ActionabilityStrategyKind.WAIT_AND_RETRY,
                    suggested_wait_ms=metadata.get("observation_window_ms"),
                )
            )

        return ProviderResult(
            action=ActionabilityStrategy(
                confidence=1.0,
                reasoning=(
                    "collector_metadata reports no change in the target's "
                    "observed state during the collection window — no evidence "
                    "waiting would help."
                ),
                raw_response="",
                reason=ActionabilityReason.VISIBLE,
                strategy=ActionabilityStrategyKind.NO_SAFE_RECOVERY,
            )
        )

    def health_check(self) -> bool:
        """Always available — no network dependency, no model to be
        missing. Present only for BaseProvider interface parity."""
        return True
