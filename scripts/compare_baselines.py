"""
compare_baselines.py

Sprint 8 (Gap #9) — runs a zero-LLM baseline provider and OllamaProvider
(llama3.2) against the SAME HealingContext, so the comparison is fair:
neither provider sees a context the other didn't, and no result depends
on run-to-run DOM/timing differences between two separate collections.

NOT a pytest test and NOT wired into CI. Per LEARNINGS.md "Sprint 8
(pre-coding)": this answers "is there a difference" once, at small
scale, against the two ground-truth shapes already live-verified for
the LLM path in Sprint 6B — it is deliberately NOT the full
CHAOS_LEVELS × shadow_dom Benchmark Runner Sprint 8/9 will eventually
build. Run manually, read the printed comparison, decide what's next.

REQUIRES (same as any other live run in this project — see README.md
Quickstart): Chaos App running (`cd chaos_app && npm run dev`) with the
scenario's required config, and Ollama running locally with llama3.2
pulled.

USAGE:
    # locator_resolution — chaos_app/.env needs selector_rotation active
    # (VITE_CHAOS_LEVEL=LOW or higher), VITE_VISIBILITY_DELAY_MODE=off,
    # VITE_POINTER_EVENTS_OVERLAY_ENABLED=false
    python -m scripts.compare_baselines --scenario locator_resolution --runs 3

    # visible_permanent — chaos_app/.env needs
    # VITE_VISIBILITY_DELAY_MODE=permanent
    python -m scripts.compare_baselines --scenario visible_permanent

    # visible_transient — chaos_app/.env needs
    # VITE_VISIBILITY_DELAY_MODE=transient, VITE_VISIBILITY_DELAY_MS=30500
    # (see LEARNINGS.md "A wrong first attempt at TRANSIENT reveals a
    # real architectural fact" for why 30500, not something shorter)
    python -m scripts.compare_baselines --scenario visible_transient

Results print to the terminal AND append to
baseline_comparison_results.jsonl (one line per run, same JSON-lines
convention as healing_decisions.log) so multiple small runs can be
aggregated later without re-running anything.

GROUND TRUTH — how each scenario's "correct" answer is known:
  locator_resolution: no fixed ground truth string (the rotated suffix
    changes every mount) — instead, each provider's proposed_selector is
    independently verified against the LIVE page after the fact
    (page.locator(selector).count() == 1). This checks the SAME thing
    Healer's own retry would check — Option C's "technical success"
    framing (see LEARNINGS.md Gap #11), not business correctness.
  visible_permanent / visible_transient: ground truth is the scenario
    itself, chosen via --scenario, matching the exact two shapes
    live-verified against llama3.2 in Sprint 6B
    ("VISIBLE/PERMANENT confirmed live", "VISIBLE/TRANSIENT confirmed
    live") — permanent => NO_SAFE_RECOVERY is correct,
    transient => WAIT_AND_RETRY is correct.
"""
import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from config.settings import Settings
from pages.chaos_login_page import ChaosLoginPage
from phoenix.ai.heuristic_provider import HeuristicProvider
from phoenix.ai.ollama_provider import OllamaProvider
from phoenix.ai.policy_only_provider import PolicyOnlyProvider
from phoenix.collector.context_collector import ContextCollector
from phoenix.healing.actions import ActionabilityStrategyKind

RESULTS_PATH = "baseline_comparison_results.jsonl"

# Ground truth per scenario — see module docstring. None for
# locator_resolution: correctness there is checked live against the
# page instead of against a fixed expected value.
_EXPECTED_STRATEGY = {
    "visible_permanent": ActionabilityStrategyKind.NO_SAFE_RECOVERY,
    "visible_transient": ActionabilityStrategyKind.WAIT_AND_RETRY,
}

# Which baseline provider handles which scenario — kept as an explicit
# mapping (not inferred from the scenario name pattern, not derived
# from the action's class/module) so it's independently unit-testable
# and can't silently drift out of sync with the branching logic below.
# Caught during development: an earlier version derived this from
# type(action).__module__, which is always "phoenix.healing.actions"
# for BOTH baseline providers (that's just where the action dataclasses
# live) — the logged field was silently identical for every scenario.
_BASELINE_PROVIDER_NAME = {
    "locator_resolution": "HeuristicProvider",
    "visible_permanent": "PolicyOnlyProvider",
    "visible_transient": "PolicyOnlyProvider",
}


def _trigger_failure(page, scenario: str, settings: Settings):
    """
    Performs the real Playwright action expected to fail for this
    scenario, and returns the caught PlaywrightTimeout. Deliberately
    calls page.locator(...).fill(...) directly rather than going through
    BasePage.fill(healing=True) — this script needs to intercept the
    failure BEFORE any Healer/provider decision, to build one shared
    HealingContext both providers will see, not two separately-collected
    ones from two separate healing attempts.

    No timeout override for visible_transient — Playwright's own true
    default (30000ms for fill()) must be left alone, since the whole
    point of VITE_VISIBILITY_DELAY_MS=30500 is to land just after that
    window expires (see LEARNINGS.md, same reference as module
    docstring). Overriding it here would silently break that scenario.
    """
    login_page = ChaosLoginPage(page, settings)
    login_page.open()

    if scenario == "locator_resolution":
        selector, value = login_page.INPUT_USERNAME, "admin"
    else:
        # Both visible_permanent and visible_transient target the
        # password field — see visibilityDelay.jsx / README.md's Chaos
        # Levels section: the mechanism hides the password input.
        selector, value = login_page.INPUT_PASSWORD, "secret"

    try:
        page.locator(selector).fill(value)
    except PlaywrightTimeout as e:
        return selector, "fill", e

    raise RuntimeError(
        f"Expected '{selector}' to fail for scenario '{scenario}' but it "
        f"succeeded — check chaos_app/.env matches this scenario's "
        f"required config (see this script's module docstring)."
    )


def _check_selector_resolves_live(page, selector: str) -> bool:
    """
    locator_resolution's correctness check: does the PROPOSED selector
    actually resolve to exactly one real element on the live page right
    now? Deliberately the same "did the technical action become
    possible again" question Healer's own retry would ask — not a
    judgment of business correctness (see LEARNINGS.md Gap #11 / Option
    C framing). An empty proposed_selector always fails this check.
    """
    if not selector:
        return False
    try:
        return page.locator(selector).count() == 1
    except Exception:
        # A malformed selector string (e.g. invalid CSS from a bad LLM
        # response) raising here IS a correctness failure, not a script
        # bug — same as it would be for Healer's own retry attempt.
        return False


def _action_to_dict(action) -> dict:
    return asdict(action) if is_dataclass(action) else {"repr": repr(action)}


def _run_once(scenario: str, run_index: int, headed: bool) -> dict:
    settings = Settings()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page()

        try:
            selector, original_code, error = _trigger_failure(page, scenario, settings)
            context = ContextCollector(page).collect(selector, error, original_code)

            llm_result = OllamaProvider(settings).analyze_failure(context)

            if scenario == "locator_resolution":
                baseline_result = HeuristicProvider().analyze_failure(context)
                baseline_correct = _check_selector_resolves_live(
                    page, baseline_result.action.proposed_selector
                )
                llm_correct = _check_selector_resolves_live(
                    page, llm_result.action.proposed_selector
                )
            else:
                baseline_result = PolicyOnlyProvider().analyze_failure(context)
                expected = _EXPECTED_STRATEGY[scenario]
                baseline_correct = baseline_result.action.strategy == expected
                llm_correct = llm_result.action.strategy == expected

            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scenario": scenario,
                "run_index": run_index,
                "broken_selector": selector,
                "baseline_provider": _BASELINE_PROVIDER_NAME[scenario],
                "baseline_action": _action_to_dict(baseline_result.action),
                "baseline_correct": baseline_correct,
                "llm_action": _action_to_dict(llm_result.action),
                "llm_correct": llm_correct,
                "llm_input_tokens": llm_result.input_tokens,
                "llm_output_tokens": llm_result.output_tokens,
                "llm_elapsed_ms": llm_result.elapsed_ms,
            }
            return record
        finally:
            browser.close()


def _print_record(record: dict) -> None:
    print("=" * 70)
    print(f"scenario={record['scenario']}  run={record['run_index']}")
    print(f"broken_selector={record['broken_selector']}")
    print("-" * 70)
    print(f"BASELINE ({record['baseline_provider']}):")
    print(f"  action:    {record['baseline_action']}")
    print(f"  correct:   {record['baseline_correct']}")
    print("-" * 70)
    print("LLM (llama3.2):")
    print(f"  action:    {record['llm_action']}")
    print(f"  correct:   {record['llm_correct']}")
    print(
        f"  cost:      {record['llm_input_tokens']} in / "
        f"{record['llm_output_tokens']} out / {record['llm_elapsed_ms']}ms"
    )
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["locator_resolution", "visible_permanent", "visible_transient"],
    )
    parser.add_argument("--runs", type=int, default=1, help="Number of repeated runs.")
    parser.add_argument(
        "--headed", action="store_true", help="Show the browser window (default: headless)."
    )
    args = parser.parse_args()

    print(
        f"Running {args.runs} sample(s) for scenario='{args.scenario}'. "
        f"Make sure chaos_app is running with matching config (see this "
        f"script's module docstring) and Ollama has llama3.2 pulled."
    )

    with open(RESULTS_PATH, "a", encoding="utf-8") as f:
        for i in range(1, args.runs + 1):
            record = _run_once(args.scenario, i, args.headed)
            _print_record(record)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nAppended {args.runs} record(s) to {RESULTS_PATH}.")


if __name__ == "__main__":
    main()
