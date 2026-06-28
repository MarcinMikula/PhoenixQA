# Gaps — thematic index

Short-form index of every numbered architectural gap identified so far.
Each entry is a 1-2 line summary + status. **Full reasoning, examples, and
resolution details live in `LEARNINGS.md`** — this file is a map, not a
copy. Use it to quickly check "what's still open" without scrolling
through the full chronological journal.

Gaps are numbered in the order they were raised, not by severity or sprint.

| # | Gap | Status | One-line summary |
|---|-----|--------|-------------------|
| 1 | Healing correctness definition | 🟡 Named, not resolved | "Test passes" ≠ "fix is correct" — no formal definition yet of what a CORRECT heal means, only that one is needed before Sprint 6 |
| 2 | Confidence score in LLM response | 🟢 Resolved | `HealingProposal.confidence` scaffolded since Sprint 0, populated for real in Sprint 3 |
| 3 | Post-heal business validation | 🟡 Named, scoped to Sprint 4/5 | "Selector now resolves" ≠ "the intended action actually happened" (toast appeared, record saved, etc.) |
| 4 | Selector healer vs UI automation healer scope | 🟡 Resolved via staged scope | Real-world failures (confirmed via Salesforce experience) are mostly timing/detachment, not selector renaming. `FailureType` enum + routing built now; only `SELECTOR_NOT_FOUND` implemented in Sprint 2-4. Other types are a **required**, not optional, future sprint |
| 5 | No failure classifier component | 🟡 Partially resolved | `classify_playwright_error()` exists and works for `SELECTOR_NOT_FOUND` (Sprint 2/4); still no strategy for the other `FailureType` values |
| 6 | No ground truth model for self-training | 🟡 Partially resolved | Safe Mode's human accept/reject (Sprint 4) is the ground truth signal; versioning/aggregation model still undefined, deferred to Sprint 6 |
| 7 | No cost accounting (tokens, storage, runtime) | 🔴 Open | No token budgets, snapshot size limits, retention policy, or runtime budget defined yet — deliberately deferred until real numbers exist |
| 8 | Screenshot under-weighted vs DOM snapshot | 🔴 Open | `screenshot_path` field exists but has had zero design attention; undecided whether it's part of the v1 prompt at all |
| 9 | Missing baseline comparison (no-healer / heuristic / LLM) | 🟡 Resolved architecturally, not yet built | `HeuristicProvider` planned as an **experimental control** (not a product feature) for Sprint 7/8, to prove the LLM is actually adding value over cheap fuzzy matching. Does NOT depend on historical fingerprinting — anchors on the present DOM, not the past |
| 10 | Missing stop conditions for Autonomous Mode | 🟡 Resolved architecturally, Sprint 5 in progress | `HealingBudget`/`AutonomousPolicy` designed (total attempts, tokens, time, confidence threshold) — required before Autonomous Mode can be considered shippable |
| 11 | Confidence ≠ correctness | 🟡 Resolved architecturally (deliberately NOT fully closed) | An LLM can be 100% confident and still point at the wrong element. Resolved by keeping business/correctness validation OUT of Healer entirely — stays the test's responsibility (Option B), with Healer only checking technical retry success (Option C framing). Deeper validation hooks deferred until real usage justifies them |

## Status legend
- 🔴 Open — named, not yet addressed at all
- 🟡 Partially resolved / scoped — architecture or plan exists, implementation pending
- 🟢 Resolved — implemented and verified

## Where to read more
Search `LEARNINGS.md` for `Gap #N` to find the full discussion, reasoning,
and any code examples for a specific gap.