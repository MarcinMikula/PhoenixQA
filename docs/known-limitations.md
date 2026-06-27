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
  `NotImplementedError` by design. Confirmed via hands-on Salesforce
  Lightning experience that these are likely MORE common in real
  enterprise apps than selector renaming — this is a required future
  sprint, not a nice-to-have.
- **Chaos App has no mechanism simulating component remount /
  detach-mid-action.** Needed before `DETACHED_FROM_DOM` handling can
  even be tested, let alone implemented.
- **Autonomous Mode is fully unimplemented and deliberately blocked.**
  `Healer.attempt_heal()` raises `NotImplementedError` if
  `HEALING_MODE=autonomous` — won't be unblocked until stop conditions
  (`max_attempts`/`max_cost_per_test`/`max_time_per_heal`) exist.

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

## Environment / tooling quirks (not project bugs, but easy to trip on)

- **`pytest -s` is required for Safe Mode to work at all.** Without it,
  pytest captures stdin/stdout and the human-review `input()` prompt
  never reaches the terminal — the run just hangs with no explanation.
- **Corporate SSL inspection breaks `npm install` and `playwright
  install`** on some networks (`UNABLE_TO_VERIFY_LEAF_SIGNATURE`).
  Workarounds used: `npm config set strict-ssl false` and
  `$env:NODE_TLS_REJECT_UNAUTHORIZED="0"` (Windows PowerShell), both
  scoped to the install step only.

## Where to read more
Search `LEARNINGS.md` for the relevant heading phrasing above (e.g.
"Known fragility, deliberately not fixed in Sprint 2") for full context,
the original failure mode, and any code snippets.
