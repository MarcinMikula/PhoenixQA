# Known limitations — thematic index

Things that are known to be incomplete, fragile, or out of scope right
now — by design or by explicit deferral, not by oversight. Each entry
notes whether it's tracked as a future TODO. **Full reasoning lives in
`LEARNINGS.md`** — this file is a map, not a copy.

## Scope boundaries (intentional, not bugs)

- **`healing=True` only exists on `click()`/`fill()`.** `navigate()`,
  `is_visible()`, and `get_text()` have no healing path at all. Surfaced
  concretely when `test_invalid_credentials` failed on `MSG_ERROR`
  despite successful click/fill healing elsewhere in the same test.
  Whether read-only assertions should be healable — and what "healing"
  even means for a boolean-returning check — is an open design question,
  not yet decided.
- **Only 2 of 5 `ActionabilityReason` values have a real collection
  strategy.** `RECEIVES_EVENTS` and `VISIBLE` are implemented, unit-tested,
  and live-verified (both against real Chaos App mechanisms —
  `pointerEventsOverlay.jsx` and `visibilityDelay.jsx` — and both
  directions of `actionability_policy.py`'s guardrail). `ENABLED`/
  `EDITABLE` are not started. `STABLE` is blocked — no deterministic
  Chaos App mechanism exists to test it against, same non-determinism
  problem already deprioritized for `DETACHED_FROM_DOM` in Sprint 6A.
  The dormant `FailureCategory.REFERENCE` (successor to
  `DETACHED_FROM_DOM`) has no active collector or plan — see
  `LEARNINGS.md` "Sprint 6A conclusion" and `docs/gaps.md` Gap #4.
- **Even where an `ActionabilityStrategy` is correctly proposed and
  validated, `Healer` never executes it.** `Healer` explicitly rejects
  any action that isn't a `SelectorReplacement` (see `healer.py`,
  `phoenix/healing/actions.py`) — for `RECEIVES_EVENTS`/`VISIBLE` this
  means the full pipeline (collect → prompt → parse → policy-correct)
  runs for real, produces a real, guardrail-validated proposal, and then
  that proposal is thrown away and the original `PlaywrightTimeout`
  surfaces to pytest unchanged. Executing an approved
  `ActionabilityStrategy` (e.g. actually waiting N ms and retrying) is a
  genuinely separate architectural question — see `docs/gaps.md` Gap #12
  and `LEARNINGS.md` "Scope of the actionability provider slice."
- **The classifier's dependence on Playwright's undocumented diagnostic
  text is a live, ongoing risk, not a historical one.**
  `parse_playwright_call_log()` (the fix for the old
  `classify_playwright_error()` substring-matching bug — see
  `LEARNINGS.md` "Sprint 6B (decision)") is verified against 8 real
  captured call logs, but depends entirely on Playwright's
  human-readable wording (`"locator resolved to"`,
  `"intercepts pointer events"`, etc.), not a supported API contract. A
  future Playwright version bump could silently break it. See
  `docs/gaps.md` Gap #13.
- **Chaos App's component remount mechanism is verified live and did
  NOT reproduce `DETACHED_FROM_DOM` against `Locator`-based
  interactions in four escalating attempts.** `chaos_app/src/chaos/
  componentRemount.jsx` (Sprint 6A) was tested with a 200-800ms random
  interval, tightened to 100-300ms, then to 10-30ms, then finally a
  deterministic `mousedown`-triggered remount with zero timing
  randomness — and none produced a classifiable failure. The most
  plausible explanation, consistent with Playwright's own documentation
  and issue tracker (`Locator.click()` is documented to retry
  automatically on mid-action detachment), is that this project's
  specific interaction pattern doesn't reach the failure the mechanism
  was built to simulate — not that the mechanism itself is broken. This
  is scoped deliberately: it isn't a claim that `Locator` is immune to
  detachment failures under every version or interaction shape, only
  that four increasingly aggressive attempts against this codebase's
  actual usage didn't produce one — see `LEARNINGS.md` "Sprint 6A
  conclusion" for the full investigation and sources. Both
  `RemountTrigger.TIMEOUT` and `RemountTrigger.MOUSEDOWN` are
  implemented and verified not to reproduce the target failure;
  `RemountTrigger.STATE_CHANGE`/`NETWORK_RESPONSE` remain declared but
  unimplemented, and are not currently planned to be pursued given this
  result. The classifier's `DETACHED_FROM_DOM` substring matches remain
  unconfirmed against a real captured Playwright error message — a
  low-priority gap now, given the failure type's deprioritization.
- **Autonomous Mode is fully unimplemented and deliberately blocked.**
  `Healer.attempt_heal()` raises `NotImplementedError` if
  `HEALING_MODE=autonomous` — won't be unblocked until stop conditions
  (`max_attempts`/`max_cost_per_test`/`max_time_per_heal`) exist.
  *(Historical note: this was true prior to Sprint 5. Autonomous Mode has
  since been implemented and verified live — see `LEARNINGS.md` Sprint 5.
  Left here as-is as a record of the state at the time this limitation
  was first written; not a currently accurate limitation.)*

## Remaining scope boundary (Sprint 6C-D onward — architecture done, coverage partial)

The `HealingAction` hierarchy, router-based `ContextCollector`, and
split prompt modules are all implemented (see `LEARNINGS.md` Sprint 6B
implementation entries) — this is no longer a "decided but not built"
boundary, just an incomplete-coverage one:

- **`ProviderResult.proposal` was renamed to `ProviderResult.action`**,
  typed as `HealingAction`; `Healer`/`safe_mode.py`/`decision_logger.py`
  all consume it. `SelectorReplacement` (`LOCATOR_RESOLUTION`) and
  `ActionabilityStrategy` (`RECEIVES_EVENTS`/`VISIBLE`) are both
  produced end-to-end; `RetryStrategy` (`REFERENCE`) is declared only —
  no collector or provider produces it, and none is currently planned.
- **`ContextCollector` is a router** (`phoenix/collector/context_collector.py`)
  dispatching to `LocatorResolutionCollector`, `ActionabilityCollector`,
  and a dormant `ReferenceCollector` by `FailureCategory` — no more
  if/elif ladder.
- **`phoenix/ai/prompts/` exists and holds `actionability_prompt.py` /
  `visible_prompt.py`**, but the original selector-healing prompt is
  still `phoenix/ai/prompt_templates.py`, not yet migrated into the same
  package — explicitly deferred cleanup (see `LEARNINGS.md` "Future
  cleanup, explicitly deferred, not forgotten"), not an oversight.

## Known fragility (tracked, not yet fixed)

- **`outerHTML` string re-matching collides on identical elements.**
  `LocatorResolutionCollector` (moved here unchanged in the Sprint 6B
  router split — still the original Sprint 2 logic) re-finds a scored
  candidate by matching its `outerHTML` string a second time — two
  structurally identical elements (e.g. `TicketList`'s three rows) would
  collide, with whichever matches first winning regardless of which was
  actually scored. Still-open TODO: replace with a retained
  `ElementHandle` from the original scoring call.
- **`LocatorResolutionCollector` makes up to 4 `page.evaluate()`
  round-trips per failure.** Correctness was prioritized over
  performance in Sprint 2; revisit once real cost/timing data exists.
- **No retention policy for `healing_decisions.log`.** It's an
  append-only file with no size cap or rotation — fine for Sprint 4
  testing, will need addressing before any long-running use.

## Things observed but not yet decided

- **Screenshot capture (`HealingContext.screenshot_path`) has had zero
  design attention.** The field exists since Sprint 0; whether it's
  actually part of the v1 LLM prompt (multimodal) or explicitly deferred
  has never been decided — see Gap #8 in `docs/gaps.md`.
- **No cost accounting anywhere** — no prompt token budgets, no DOM
  snapshot storage size limits, no history retention policy, no
  benchmark wall-clock budget. Deliberately premature to size these
  before Sprint 3/4 produce real numbers — see Gap #7 in `docs/gaps.md`.
- **"Healing correctness" has no formal definition.** A test passing
  after a heal doesn't guarantee the fix was actually correct (e.g. an
  LLM could widen a selector to something that technically matches but
  clicks the wrong element). Must be resolved before Sprint 6's history
  schema is designed — see Gap #1 in `docs/gaps.md`.
- **The decided `FailureCategory`/`ActionabilityReason` model has two
  known, explicitly tracked limits, not fully solved by adopting it.**
  Gap #13: the model depends entirely on Playwright's undocumented,
  unversioned diagnostic text — a future Playwright upgrade could
  silently break the parser the same way this project's own hand-crafted
  message assumptions have already twice turned out wrong (Sprint 4,
  Sprint 6B), without Playwright changing anything. Gap #14: even with
  the corrected `LOCATOR_RESOLUTION` naming, the collector still can't
  tell apart genuine selector drift from a conditionally-not-yet-mounted
  element or an unexpected app state — Playwright's message is identical
  in all three cases. See `docs/gaps.md` Gap #13/#14 and `LEARNINGS.md`
  "Sprint 6B (decision)".

## Environment / tooling quirks (not project bugs, but easy to trip on)

- **`VITE_VISIBILITY_DELAY_MS=30500`'s margin against `ActionabilityCollector`'s
  observation window is too tight — caught live, causes real flakiness.**
  `_VISIBLE_OBSERVATION_WINDOW_MS = 1200`, starting right after
  Playwright's own `fill()` timeout (`30000ms` default) expires. `30500`
  leaves only a `500ms` margin for the reveal to land inside that
  `1200ms` window — less than the window itself is wide. Confirmed live
  (Sprint 8): two back-to-back test runs of the identical mechanism got
  different results (`NO_SAFE_RECOVERY` then `WAIT_AND_RETRY`) purely
  from system-jitter timing variance around this margin, not a code bug
  — see `LEARNINGS.md`'s "[Verification] Live confirmation" entry.
  Recommended: `VITE_VISIBILITY_DELAY_MS=32000` or higher until this is
  re-tested and the margin formally revisited.
- **`pytest -s` is required for Safe Mode to work at all.** Without it,
  pytest captures stdin/stdout and the human-review `input()` prompt
  never reaches the terminal — the run just hangs with no explanation.
- **Corporate SSL inspection breaks `npm install` and `playwright
  install`** on some networks (`UNABLE_TO_VERIFY_LEAF_SIGNATURE`).
  Workarounds used: `npm config set strict-ssl false` and
  `$env:NODE_TLS_REJECT_UNAUTHORIZED="0"` (Windows PowerShell), both
  scoped to the install step only.
- **`.env.example` changes never reach either real `.env` file
  automatically, on either side of this repo.** Confirmed twice now
  (Sprint 5: `OLLAMA_MODEL`/`HEALING_MODE`; Sprint 6A:
  `VITE_COMPONENT_REMOUNT_ENABLED`). When something "should have
  changed" but the app's behavior didn't, check the actual gitignored
  `.env` file directly before suspecting the code.
- **Testing an `ACTIONABILITY` scenario against a FIXED selector
  requires `selector_rotation` to be explicitly forced OFF via
  `VITE_OVERRIDE_SELECTOR_ROTATION=false`** — leaving `VITE_CHAOS_LEVEL`
  at any of `LOW`/`MEDIUM`/`HIGH` (all three include `selector_rotation`)
  means the target field's fixed `data-testid` never resolves AT ALL,
  regardless of the actionability mechanism (`visibilityDelay.jsx`,
  `pointerEventsOverlay.jsx`) also being active. Per
  `failure_classifier.py`'s `parse_playwright_call_log()`: no `"locator
  resolved to"` marker anywhere in Playwright's message means
  `LOCATOR_RESOLUTION`, unconditionally — the visibility/pointer-events
  mechanism never even gets a chance to matter, and
  `PolicyOnlyProvider`/`OllamaProvider`'s actionability path is never
  reached. Caught live (Sprint 8): a `visible_permanent` run raised
  `PolicyOnlyProvider`'s own `NotImplementedError` for
  `category=LOCATOR_RESOLUTION` immediately after a `locator_resolution`
  scenario run had (correctly) required the OPPOSITE override state —
  the two scenarios need genuinely different `.env` configs, not just
  different `VITE_VISIBILITY_DELAY_MODE` values. See `LEARNINGS.md`
  "Sprint 8 (pre-coding)" verification entries for the exact configs
  used for each scenario.

## Where to read more
Search `LEARNINGS.md` for the relevant heading phrasing above (e.g.
"Known fragility, deliberately not fixed in Sprint 2", "Sprint 6A
conclusion") for full context, the original failure mode, and any code
snippets.