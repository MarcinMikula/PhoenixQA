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
- **Only `FailureType.SELECTOR_NOT_FOUND` has a real collection strategy.**
  `DETACHED_FROM_DOM`, `NOT_VISIBLE`, `TIMEOUT_WAITING` raise
  `NotImplementedError` by design. The original Sprint 2 assumption that
  `DETACHED_FROM_DOM` would be the most common of the three (from direct
  Selenium/Salesforce Lightning experience) was empirically tested in
  Sprint 6A and did not hold for a `Locator`-based framework — see
  `LEARNINGS.md` "Sprint 6A conclusion" and `docs/gaps.md` Gap #4.
  `classify_playwright_error()` DOES correctly recognize `DETACHED_FROM_DOM`
  (verified live), but `ContextCollector` still raises `NotImplementedError`
  for it, and building the collector is no longer the planned next step.
  Sprint 6B diagnostics (see below) further found that a flat choice
  between `NOT_VISIBLE`/`TIMEOUT_WAITING` isn't the right next move
  either — the exact shape of the next collection strategy is an open
  decision, not just a pick between the two existing enum members.
- **`classify_playwright_error()` currently misclassifies actionability
  failures as `SELECTOR_NOT_FOUND` — confirmed live, not just suspected,
  and a fix is decided but not yet implemented.** A `click()`/`fill()`
  timeout on an element that resolves but fails an actionability check
  (not visible, disabled, readonly, animating, covered by an overlay)
  produces a message containing `"waiting for locator"`, the same
  substring the classifier checks for `SELECTOR_NOT_FOUND` — so it's
  routed into the selector-healing pipeline even though the selector is
  completely correct and nothing about it needs replacing. Confirmed via
  real `healing_decisions.log` entries plus six throwaway diagnostic
  tests covering all five Playwright actionability reasons
  (`visible`/`enabled`/`editable`/`stable`/`receives events`).
  `async_delay`'s current implementation (conditional DOM mounting, not
  CSS-based hiding) happens to produce the exact same message shape as
  genuine `SELECTOR_NOT_FOUND` — meaning it cannot currently be used to
  exercise a true "resolved but not actionable" case at all; a future
  chaos mechanism aimed at that case would need to render the element
  immediately and toggle a CSS/attribute property instead. The fix is a
  decided replacement — `parse_playwright_call_log() -> ClassifiedFailure`
  with `FailureCategory`/`ActionabilityReason` — not yet written in code.
  See `LEARNINGS.md` "Sprint 6B (decision)" and `docs/gaps.md` Gap #5.
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

## Scope boundary about to change (Sprint 6B onward — decided, not yet built)

**Note (post Sprint 6A):** the `HealingAction` hierarchy, polymorphic
`ContextCollector`, and split prompt modules below remain the committed
Sprint 6+ architecture regardless of target failure type. `DETACHED_FROM_DOM`
specifically has been deprioritized (see `LEARNINGS.md` Sprint 6A
conclusion, `docs/gaps.md` Gap #4) — the bullets below describe
architecture that will land against whichever of `NOT_VISIBLE`/
`TIMEOUT_WAITING` is chosen next, not necessarily `DETACHED_FROM_DOM`.

- **`HealingProposal` is still the only provider return shape in the
  codebase today.** A `HealingAction` hierarchy (`SelectorReplacement`,
  `RetryStrategy`, `WaitStrategy`, `VisibilityStrategy`) has been decided
  architecturally for Sprint 6 but not yet implemented — `ProviderResult.
  proposal` still exists; the planned rename to `ProviderResult.action`
  and the accompanying `Healer`/`safe_mode.py`/`decision_logger.py`/
  `response_parser.py` updates are pending. Until that refactor lands,
  do not assume any non-selector failure type can produce a structured
  proposal — only `SelectorReplacement`-shaped output is wired end to
  end.
- **`ContextCollector` is still a single class with an if/elif-shaped
  routing method**, not yet the planned `BaseContextCollector` subclass
  router. The Sprint 6 refactor (moving `_collect_selector_context` into
  `collectors/selector_collector.py` unchanged, and adding a collector
  for whichever failure type is chosen next) has been decided but not
  implemented.
- **`prompt_templates.py` is still one module**, not yet split into
  `phoenix/ai/prompts/` per failure type. Planned for the sub-sprint
  that replaces the original Sprint 6C.

## Known fragility (tracked, not yet fixed)

- **`outerHTML` string re-matching collides on identical elements.**
  `ContextCollector` re-finds a scored candidate by matching its
  `outerHTML` string a second time — two structurally identical elements
  (e.g. `TicketList`'s three rows) would collide, with whichever matches
  first winning regardless of which was actually scored. Sprint 3 TODO:
  replace with a retained `ElementHandle` from the original scoring call.
- **`context_collector.py` makes up to 4 `page.evaluate()` round-trips
  per failure.** Correctness was prioritized over performance in Sprint
  2; revisit once Sprint 3/4 give real cost/timing data.
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

## Where to read more
Search `LEARNINGS.md` for the relevant heading phrasing above (e.g.
"Known fragility, deliberately not fixed in Sprint 2", "Sprint 6A
conclusion") for full context, the original failure mode, and any code
snippets.