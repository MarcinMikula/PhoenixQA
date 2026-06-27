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

## Documentation structure

- **`LEARNINGS.md` stays chronological** (problem → analysis → decision
  → implementation → test → conclusion, per sprint) — it's the project's
  journal, showing the actual thinking process, not just outcomes.
- **Thematic indexes (`docs/*.md`) summarize and link, never duplicate**
  full content. One source of truth per fact; indexes exist for fast
  lookup, not as a second copy to keep in sync.

## Where to read more
Search `LEARNINGS.md` for the bolded decision phrasing above (e.g.
"Decision: ground truth logging") to find the full reasoning and any
rejected alternatives.
