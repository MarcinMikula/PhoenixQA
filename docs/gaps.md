# Gaps — thematic index

Short-form index of every numbered architectural gap identified so far.
Each entry is a 1-2 line summary + status. **Full reasoning, examples, and
resolution details live in `LEARNINGS.md`** — this file is a map, not a
copy. Use it to quickly check "what's still open" without scrolling
through the full chronological journal.

**Not the same as [`docs/research_hypotheses.md`](research_hypotheses.md):**
a gap here is an architectural TODO — something to build or decide. A
research hypothesis is an open empirical question — something to find
out through evidence, often only answerable once the Sprint 7/8
benchmark runner exists. Some gaps (e.g. #9) exist specifically to
produce the tooling a related hypothesis needs to be answered — building
the tool isn't the same as answering the question.

Gaps are numbered in the order they were raised, not by severity or sprint.

| # | Gap | Status | One-line summary |
|---|-----|--------|-------------------|
| 1 | Healing correctness definition | 🟡 Named, not resolved | "Test passes" ≠ "fix is correct" — no formal definition yet of what a CORRECT heal means, only that one is needed before Sprint 6 |
| 2 | Confidence score in LLM response | 🟢 Resolved | `HealingProposal.confidence` scaffolded since Sprint 0, populated for real in Sprint 3 |
| 3 | Post-heal business validation | 🟡 Named, scoped to Sprint 4/5 | "Selector now resolves" ≠ "the intended action actually happened" (toast appeared, record saved, etc.) |
| 4 | Selector healer vs UI automation healer scope | 🟡 Narrowed after a controlled experiment | Sprint 2 assumed `detached_from_dom` would dominate real-world failures, based on Selenium/`ElementHandle`-style Salesforce Lightning experience. Sprint 6A built a real reproduction mechanism and ran four escalating attempts (200-800ms → deterministic `mousedown` trigger) — none reproduced against this project's `Locator`-based interaction pattern, consistent with Playwright's documentation stating that `Locator.click()` retries automatically on mid-action detachment. Real "not attached" errors in `Locator`-based suites do occur elsewhere, tracing to `ElementHandle` misuse, a narrow version-specific edge case, or a sub-frame actionability-to-dispatch race fixed via locator anchoring, not selector/retry healing. Deprioritized based on current evidence, not proven impossible — `FailureType` enum unchanged; Sprint 6B redirected to `NOT_VISIBLE`/`TIMEOUT_WAITING` (decision pending). See `LEARNINGS.md` Sprint 6A conclusion |
| 5 | No failure classifier component | 🟡 Partially resolved | `classify_playwright_error()` exists and works for `SELECTOR_NOT_FOUND` (Sprint 2/4) and `DETACHED_FROM_DOM` (Sprint 6A, classification confirmed, but the failure type itself deprioritized — see Gap #4); still no strategy for `NOT_VISIBLE`/`TIMEOUT_WAITING` |
| 6 | No ground truth model for self-training | 🟡 Partially resolved | Safe Mode's human accept/reject (Sprint 4) is the ground truth signal; versioning/aggregation model still undefined, deferred to Sprint 6 |
| 7 | No cost accounting (tokens, storage, runtime) | 🔴 Open | No token budgets, snapshot size limits, retention policy, or runtime budget defined yet — deliberately deferred until real numbers exist |
| 8 | Screenshot under-weighted vs DOM snapshot | 🔴 Open | `screenshot_path` field exists but has had zero design attention; undecided whether it's part of the v1 prompt at all |
| 9 | Missing baseline comparison (no-healer / heuristic / LLM) | 🟡 Resolved architecturally, not yet built | `HeuristicProvider` planned as an **experimental control** (not a product feature) for Sprint 7/8, to prove the LLM is actually adding value over cheap fuzzy matching. Does NOT depend on historical fingerprinting — anchors on the present DOM, not the past |
| 10 | Missing stop conditions for Autonomous Mode | 🟢 Implemented and verified live | `HealingBudget`/`AutonomousPolicy` built and unit tested (13 tests). Confirmed live against real Chaos App + Ollama: zero terminal prompts, correct auto-accept (0.85-0.95 confidence) and auto-reject (0.0, truncated JSON) behavior |
| 11 | Confidence ≠ correctness | 🟡 Resolved architecturally (deliberately NOT fully closed) | An LLM can be 100% confident and still point at the wrong element. Resolved by keeping business/correctness validation OUT of Healer entirely — stays the test's responsibility (Option B), with Healer only checking technical retry success (Option C framing). Deeper validation hooks deferred until real usage justifies them |
| 12 | "Recover selector" vs "recover action" (NEW, Sprint 6 pre-coding) | 🟡 Resolved architecturally, implementation pending | For `DETACHED_FROM_DOM` (and `NOT_VISIBLE`/`TIMEOUT_WAITING`) there is no broken selector to replace — the selector may still be correct; what failed is the in-flight ACTION. Resolved by reframing `Healer`'s job as "action recovery" with `SELECTOR_NOT_FOUND` as the special case that happens to mean "propose a new selector." Drives three follow-on decisions: polymorphic `ContextCollector`, split prompt modules, and a new `HealingAction` type hierarchy replacing `HealingProposal` as the universal return shape — see `LEARNINGS.md` Sprint 6 (pre-coding). **Reframing itself unaffected by Gap #4's DETACHED_FROM_DOM deprioritization (Sprint 6A) — still applies to whichever failure type Sprint 6B onward targets.** |

## Status legend
- 🔴 Open — named, not yet addressed at all
- 🟡 Partially resolved / scoped — architecture or plan exists, implementation pending
- 🟢 Resolved — implemented and verified

## Where to read more
Search `LEARNINGS.md` for `Gap #N` to find the full discussion, reasoning,
and any code examples for a specific gap.