# Architecture decisions — thematic index

Short-form index of key architectural decisions made across sprints,
in the order they were decided (not strictly chronological by sprint).
**Full reasoning and alternatives considered live in `LEARNINGS.md`** —
this file is a map, not a copy.

## Chaos App design

- **CHAOS_LEVELS as a dict (level → mechanism list), not a count.** A
  level represents a research scenario, not "how much chaos." Prevents
  the model from breaking when a 5th mechanism is eventually added.
- **Shadow DOM is an independent flag, not part of the level ladder.**
  It's a different AXIS of difficulty (structural access), not "more
  chaos" — combinable with any level (e.g. `HIGH + shadow_dom_enabled`).
- **Mechanism realism ranking drove implementation priority:**
  DOM Mutation (10/10) > Selector Rotation (9/10) > Async Delay (8/10) >
  Shadow DOM (5/10). DOM Mutation got the most internal variants
  (wrap/retag/unwrap) because it's the most common real-world failure
  mode; Shadow DOM stayed a simple toggle.
- **`get_mechanisms_for_level()` is the single source of truth** for
  which mechanisms are active — both the app and the future benchmark
  runner call this, no duplicated mapping logic.

## Failure classification and context collection

- **`FailureType` enum + routing function built in Sprint 2**, even
  though only `SELECTOR_NOT_FOUND` got a real implementation. Avoids
  reshaping `HealingContext` later when other failure types
  (`DETACHED_FROM_DOM`, `NOT_VISIBLE`, `TIMEOUT_WAITING`) get addressed —
  see Gap #4 in `docs/gaps.md`.
- **Context Collector scoring starts from the broken selector's name**,
  not from DOM position. Tokenize the selector → score every DOM element
  by weighted attribute match (`data-testid:5, aria-label:4, name:4,
  placeholder:3, id:2, textContent:1`) → walk up to the nearest landmark
  from the best-scoring candidate. A naive "first visible form" approach
  was caught and rejected before being built — see `LEARNINGS.md`
  "Refinement: scoring must start from the selector name."
- **Ties in scoring are kept, not arbitrarily broken.** Ambiguity is real
  information for the LLM to reason about.
- **Shadow DOM is checked in its own pass, scored alongside light DOM**,
  not as an upfront "scan everything just in case."
- **`ContextCollector` becomes a router over `BaseContextCollector`
  subclasses, one per `FailureType` (Sprint 6 pre-coding decision).**
  The Sprint 2 if/elif ladder was fine for one implemented failure type;
  extending it to `DETACHED_FROM_DOM` (and later `NOT_VISIBLE`/
  `TIMEOUT_WAITING`), each needing structurally different collected data,
  was judged to have crossed the point where a shared function body is a
  liability rather than a convenience. `selector_collector.py` carries
  today's `SELECTOR_NOT_FOUND` logic across unchanged; `context_collector.py`
  itself becomes a thin router, mirroring the existing `provider_factory.py`
  pattern. See Gap #12 in `docs/gaps.md` and `LEARNINGS.md` Sprint 6.
- **Sprint 6B diagnostics confirmed Playwright's failure model is
  two-stage, not flat — evidence gathered, exact `FailureType` shape
  NOT yet decided.** Six throwaway diagnostic tests plus real
  `healing_decisions.log` data established that Playwright's call log
  first answers "did the locator resolve at all" and only then, if it
  did, reports one of five concrete actionability reasons (`visible`,
  `enabled`, `editable`, `stable`, `receives events` — the last one
  naming the specific blocking element). This directly undercuts the
  plan to simply pick `NOT_VISIBLE` or `TIMEOUT_WAITING` as Sprint 6B's
  target, since a bare `"waiting for locator(...)"` message is
  indistinguishable from `SELECTOR_NOT_FOUND` regardless of which one
  gets chosen. Deliberately recorded as evidence, not a redesign
  decision — whether this becomes a `FailureCategory`/`ActionabilityReason`
  split, a smarter classifier keeping the existing enum, or something
  else is an open, upcoming decision. See Gap #5 in `docs/gaps.md` and
  `LEARNINGS.md` Sprint 6B.

## AI provider layer

- **Provider abstraction (Sprint 0) pays off repeatedly.** Same
  `BaseProvider` interface covers Ollama, Anthropic, and (planned)
  `HeuristicProvider` — adding a non-LLM provider for benchmarking cost
  nothing architecturally because the abstraction already existed.
- **Sprint 3 model selection: `llama3.2`, not `llava`, for verification.**
  `llava` (vision-first, older text architecture) was deliberately set
  aside to avoid debugging prompt architecture and model JSON-reliability
  as one tangled variable. Same instinct as the CHAOS_LEVELS isolation
  decision — separate the variables.
- **Response parsing is defensive by design**: strips markdown fences,
  extracts JSON from stray text, falls back to a zero-confidence proposal
  on total parse failure rather than crashing the pipeline.
- **`HeuristicProvider` (planned) is an experimental control, not a
  product feature.** Its purpose is to prove the LLM adds value over
  cheap fuzzy matching — see Gap #9 in `docs/gaps.md`.
- **Prompt templates split into one module per `FailureType` (Sprint 6
  pre-coding decision), not one prompt with conditional sections.**
  `phoenix/ai/prompts/selector_prompt.py`, `detached_prompt.py`, etc.,
  routed via a small `get_prompt_for(failure_type)` function. Reasoning:
  "find a replacement selector in this HTML" and "given this timing/
  mutation data, should the action be retried, and after what wait?" are
  different cognitive tasks for the model — conflating them into one
  prompt with branches would produce a worse prompt for both cases than
  two focused ones. See `LEARNINGS.md` Sprint 6, Decision #3.

## Autonomous Mode (Sprint 5)

- **`max_attempts` is total-per-session, with per-selector tracking as a
  diagnostic side-channel, not the actual limit.** Per-selector-only
  limits could legally allow N selectors × M attempts each in one run —
  not what a single attempts budget is meant to mean.
- **Budget is measured in tokens/time, never currency.** Providers report
  neutral `ProviderResult` facts (input/output tokens, elapsed_ms); a
  separate `HealingBudget` enforces limits. Dollar conversion is
  explicitly NOT this codebase's job — model pricing changes over time,
  token counts don't.
- **`max_time_per_heal` wraps the full collect+analyze+apply+retry
  lifecycle**, not just the LLM call — CI cares about total time spent,
  not just inference time.
- **Three distinct exception types**, not one: `HealingRejectedError`
  (bad proposal), `HealingLimitExceededError` (budget exhausted, new),
  `HealingFailedError` (provider/API crashed, new). Each tells a
  different story in a CI failure report.
- **Confidence threshold lives in a configurable `AutonomousPolicy`**,
  not a hardcoded constant — cleanly separates Safe Mode (confidence is
  informational) from Autonomous Mode (confidence is a hard gate).
- **Business/correctness validation is deliberately OUT of Healer's
  scope** (Gap #11). Three options weighed (callback param on every
  action / leave entirely to test assertions / technical-only validation
  in Healer); resolved as a layered responsibility model — Playwright
  performs the action, PhoenixQA recovers the ability to perform it,
  the test judges correctness. Avoids `Healer` absorbing test-framework
  responsibilities and an API that accumulates
  `validate=..., policy=..., hooks=...` params per call.

## Healing orchestration (Safe Mode)

- **`Healer` is lazily constructed in `BasePage`**, not built in
  `__init__` — avoids provider/collector setup cost for every page object
  instance when most never hit a failure path.
- **Ground truth logging is a JSON Lines file for Sprint 4**, not SQLite.
  Building the real `history_store.py` schema before Gap #1 (healing
  correctness definition) is resolved would mean guessing at structure
  twice.
- **Empty/zero-confidence proposals auto-reject before human review.**
  There's nothing for a human to meaningfully review in an empty
  proposal — asking anyway risks an accidental "y" leading to nonsense
  retries (confirmed: this was a real bug, caught in a live run).
- **`healing=True` only exists on `click()`/`fill()`**, never on
  `navigate()` or read-only assertions (`is_visible()`/`get_text()`).
  Infrastructure failures (server down) and selector failures are
  different problem classes — confirmed by experiment (Chaos App
  stopped → clean `ERR_CONNECTION_REFUSED`, Healer never invoked).
- **`BasePage.click()`/`fill()` catch `HealingRejectedError`/
  `HealingLimitExceededError`/`HealingFailedError` and re-raise the
  ORIGINAL Playwright exception**, not the Healer's internal one. This
  had been the documented design intent since Sprint 4/5 (see
  `healer.py`'s exception docstrings) but was never actually implemented
  until a Sprint 6A live run surfaced the mismatch — pytest was reporting
  a confusing "confidence below threshold" message instead of the real
  `TimeoutError`. The rich diagnosis stays available in
  `healing_decisions.log`; pytest's own failure report is the same clean
  one a reader would see whether or not healing was enabled at all.

## Failure type expansion (Sprint 6 pre-coding)

- **"Recover selector" is a special case of "recover action," not the
  general case (Gap #12).** `SELECTOR_NOT_FOUND` had a clean framing —
  selector stops resolving, propose a new one. `DETACHED_FROM_DOM` breaks
  that framing: the selector may still be perfectly correct, but the
  in-flight action lost its target mid-execution when the element was
  removed and replaced by the framework. `Healer`'s job for this and the
  remaining failure types is reframed as proposing a RECOVERY STRATEGY
  for an interrupted action, not a replacement locator string.
- **`HealingProposal` is retired as the universal provider return
  shape, replaced by a `HealingAction` ABC hierarchy.** Forcing
  "wait 400ms and retry" through a `proposed_selector: str` field would
  either corrupt that field's meaning everywhere it's read, or grow the
  dataclass into an ever-expanding bag of optional fields — the same
  anti-pattern already rejected once in Gap #11 for a different reason
  (a callback-per-action API). `SelectorReplacement` becomes the
  `SELECTOR_NOT_FOUND`-specific subclass; `RetryStrategy` (Sprint 6),
  `WaitStrategy` and `VisibilityStrategy` (declared now, implemented in
  later sprints) join it. `ProviderResult.proposal` becomes
  `ProviderResult.action`. Flagged as a required, blocking refactor
  touching `Healer`, `safe_mode.py`, `decision_logger.py`, and
  `response_parser.py`'s fallback path — comparable in breadth to
  Sprint 5's `HealingProposal → ProviderResult` refactor.
- **Sprint 6 is built as four vertical sub-sprints (6A-6D), one failure
  type (`DETACHED_FROM_DOM`) only, not four failure types in parallel.**
  Same instinct as Sprint 2→5's sequencing, applied one level deeper:
  6A (Chaos App mechanism + classifier only, zero healing logic), 6B
  (context collector against a live page), 6C (prompt producing a
  parseable proposal), 6D (full Healer integration, both modes). Each
  slice has historically surfaced a real bug in this project (fill() vs
  click() classifier gap in Sprint 4, mode-logging bug in Sprint 5) that
  breadth-first building would have masked.
- **Divergence over unification, reaffirmed as explicit policy.**
  PhoenixQA deliberately does not try to collapse the four failure types
  into one generic "AI fixes it" mechanism. More specialized components
  than shared logic, after Sprint 6, is read as a sign the architecture
  fits the problem — not as premature complexity.
- **`DETACHED_FROM_DOM` deprioritized for Sprint 6B onward after a
  controlled experiment (Sprint 6A), not removed from the architecture,
  and not proven impossible.** Four escalating reproduction attempts
  (200-800ms random interval down to a deterministic `mousedown`-triggered
  remount with zero timing randomness) found no reproduction against
  this project's `Locator`-based interaction pattern. Consistent with
  Playwright's own docs and issue tracker — `Locator.click()` is
  documented to retry automatically on mid-action detachment — but the
  scope of the claim is deliberately narrow: this says PhoenixQA's
  specific interaction pattern didn't produce the failure in four
  attempts, not that `Locator` is immune to it under every version or
  interaction shape. Real "not attached" errors that DO occur in
  `Locator`-based suites elsewhere trace to patterns (ElementHandle
  misuse, a narrow `check()`/`uncheck()` edge case, a sub-frame
  actionability race) that are remediated via locator-structure changes
  in practice, not selector or retry healing. Decisions above
  (action-recovery reframing, polymorphic collector, split prompts,
  `HealingAction` hierarchy) are unaffected — they generalize across
  failure types; only which failure type Sprint 6B-D actually build
  against is redirected. See `LEARNINGS.md` Sprint 6A conclusion and
  `docs/gaps.md` Gap #4.

## Documentation structure

- **`LEARNINGS.md` stays chronological** (problem → analysis → decision
  → implementation → test → conclusion, per sprint) — it's the project's
  journal, showing the actual thinking process, not just outcomes.
- **Thematic indexes (`docs/*.md`) summarize and link, never duplicate**
  full content. One source of truth per fact; indexes exist for fast
  lookup, not as a second copy to keep in sync.
- **New `LEARNINGS.md` sprint entries are tagged by phase — `[Decision]`
  / `[Implementation]` / `[Verification]` / `[Conclusion]` / `[Follow-up]`
  — in subsection headers, always in that order within a sprint.**
  Adopted after Sprint 6A, which mixed all five freely in the order
  conversations actually happened and became hard to scan at >2000 lines.
  Applies going forward only — the existing chronological history is
  deliberately NOT retrofitted (rewriting past entries into a tidier
  shape would misrepresent how the thinking actually unfolded, which is
  the whole point of keeping this file chronological in the first
  place). Sprint 6A itself got a light retrofit — phase tags added to
  its existing headers, no prose rewritten — as the one exception,
  since it was the sprint that surfaced the need for the convention.
- **Claims about what an experiment shows are scoped to what was
  actually tested, not generalized to the underlying tool or
  technology.** A run that produces a clean null result supports "not
  observed under these N conditions," not "impossible" or "resolved" —
  the distinction between "deprioritized based on current evidence" and
  "proven true/false in general" is treated as a required part of
  writing up any experimental result in `LEARNINGS.md`, not an
  optional hedge. Surfaced explicitly during Sprint 6A's `DETACHED_FROM_DOM`
  writeup, where early drafts overstated a four-attempt null result as
  an architectural impossibility rather than evidence supporting a
  scope decision.

## Commit message convention

Adopted informally across recent commits, formalized here so it doesn't
require re-deciding each time. One-line prefix + short imperative
summary, optional body for anything that isn't obvious from the diff
alone:

```
<prefix>: <short imperative summary>

<optional body — the "why", not a restatement of the diff. Link back
to a Gap # or Sprint # in LEARNINGS.md when the change traces to one.>
```

| Prefix | Use for |
|---|---|
| `docs:` | `LEARNINGS.md`, `docs/*.md`, `README.md` — no code changes |
| `feat:` | new capability (a new FailureType strategy, a new provider, a new chaos mechanism) |
| `fix:` | correcting a bug in existing behavior (e.g. the fill()/click() classifier gap, the hardcoded log mode) |
| `refactor:` | restructuring without changing behavior (e.g. `HealingProposal` → `ProviderResult`, the planned `ContextCollector` → router split) |
| `test:` | test-only changes — new unit tests, fixing a flaky test, no production code touched |

Guidance, not a hard rule: prefer one prefix per commit — a commit that's
genuinely both `feat:` and `refactor:` (e.g. Sprint 5's `HealingProposal`→
`ProviderResult` change, which was refactor-shaped but unlocked new
behavior) can pick whichever better describes the *reader-facing*
consequence, and explain the other half in the body.

Body is optional for small, self-explanatory changes (a typo fix, a
one-line default correction) but expected for anything a future reader
of `git log` would otherwise have to reconstruct from LEARNINGS.md
anyway — if the commit closes or advances a numbered Gap, say so
explicitly (`Gap #12`, `Sprint 6B`, etc.) so the commit history and the
journal stay cross-referenceable in both directions.

## Where to read more
Search `LEARNINGS.md` for the bolded decision phrasing above (e.g.
"Decision: ground truth logging") to find the full reasoning and any
rejected alternatives.