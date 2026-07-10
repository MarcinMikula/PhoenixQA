# Research hypotheses — thematic index

This file exists because `docs/gaps.md` and `docs/research_hypotheses.md`
answer two genuinely different questions, and conflating them was
starting to hide both:

- **A Gap (`docs/gaps.md`) is an architectural TODO** — something known
  to be missing, incomplete, or undecided, which the project intends to
  *build* or *resolve* by making a decision.
- **A hypothesis (this file) is an open empirical question** — something
  the project is trying to *find out*, where the answer depends on
  evidence PhoenixQA doesn't have yet, not on a design decision it hasn't
  made yet. Some hypotheses are only answerable once the Sprint 7/8
  benchmark runner exists; others already have partial answers from real
  experiments (Sprint 6A is the first example).

**Full reasoning for every entry lives in `LEARNINGS.md`** — this file is
a map, not a copy, same convention as `docs/gaps.md`. Hypotheses are
numbered in the order they were identified, not by importance.

A hypothesis and a gap can point at the same underlying topic without
being the same thing — e.g. Gap #9 (missing heuristic baseline) is the
architectural TODO "build `HeuristicProvider`"; RH-1 below is the actual
question that provider exists to answer. Building the provider doesn't
answer the question by itself — running it against the benchmark does.

| # | Hypothesis | Status | Related | One-line summary |
|---|---|---|---|---|
| 1 | Does an LLM meaningfully outperform a cheap heuristic (fuzzy/Levenshtein matching) for `selector_not_found` healing, or is most of the value achievable without one? | 🔴 Open — not yet measurable | Gap #9 | The actual experiment `HeuristicProvider` exists to run, once Sprint 7/8's benchmark runner can execute both providers against the same failure set |
| 2 | Which of PhoenixQA's four failure types actually justify LLM-based healing investment, versus being architecturally rare or trivially heuristic-solvable for a `Locator`-based framework? | 🟡 Partially answered | Gap #4, Gap #5, Gap #12, `LEARNINGS.md` Sprint 6A, Sprint 6B | `detached_from_dom` found to be a low-priority target for this project's interaction pattern (four escalating experiments, no reproduction) — see the scope caveats in that entry before generalizing further. Sprint 6B diagnostics found `not_visible`/`timeout_waiting` aren't cleanly separable failure types at all — Playwright reports five distinct actionability reasons once a locator resolves. The classification question is now resolved architecturally (`FailureCategory`/`ActionabilityReason`, decided but not implemented); which categories actually justify LLM reasoning over a cheaper heuristic (RH-1) is still fully open, and now has a cleaner shape to be tested against once built |
| 3 | Is "the retried action didn't raise" a sufficient definition of healing correctness, or does the project need an independent signal that the fix was actually right, not just technically successful? | 🔴 Open | Gap #1, Gap #11 | A confident, technically-successful heal can still point at the wrong element (Gap #11's concrete scenario). Blocks a trustworthy Sprint 6/7 Healing History schema — recording *that* a heal was accepted isn't the same as recording *whether it was correct* |
| 4 | Does DOM-snapshot context outperform screenshot (multimodal) context for healing accuracy, or is DOM alone sufficient for the failure types PhoenixQA targets? | 🔴 Open — zero design attention so far | Gap #8 | `HealingContext.screenshot_path` has existed since Sprint 0 and has never been used or evaluated. Most plausible tension: DOM alone likely explains `selector_not_found` fully, but visual layout problems (element rendered off-screen, hidden behind an overlay) may not be fully DOM-explainable — untested either way |
| 5 | Can human accept/reject feedback (Safe Mode's ground truth signal) measurably improve future healing quality via few-shot retrieval, once Healing History exists? | 🔴 Open | Gap #6 | The ground truth signal exists (Sprint 4); nothing consumes it yet. Genuinely unknown whether retrieval-based few-shotting helps this specific task or just adds latency and complexity for a marginal gain |
| 6 | Is selector/action healing economically viable compared to the maintenance cost it replaces — and is "healing rate" even the right unit to measure that in? | 🔴 Open — reframing, not yet operationalized | Gap #9, `docs/future-ideas.md` (Allure dashboard) | A number like "LLM healed 92% of failures" doesn't tell a reader what they actually care about: how much human maintenance time did this replace. A hypothetical better framing is engineering hours saved per period, benchmarked against the token/time cost of the healing pipeline itself — not yet designed, let alone measured. Worth treating as a candidate headline metric for the eventual benchmark write-up, not a replacement for the existing Pass Before/After Heal table, which still answers a different, also-useful question |
| 7 | Does model confidence reliably correlate with healing correctness across a real distribution of failures, or is the risk described in Gap #11 (confident but wrong) common enough to matter in practice? | 🟡 Partially answered | Gap #11 | Gap #11 established the *risk* is real and structurally possible; nothing yet measures how *often* it actually happens against a real benchmark run. A confidence-vs-correctness scatter, once Healing History and a correctness definition (RH-3) both exist, would answer this directly |
| 8 | Is a repeating, timing-based chaos mechanism (the `componentRemount.jsx` approach) the right way to simulate a given failure family, or do some failure classes need a different kind of mechanism to reproduce reliably (e.g. reference-holding code paths, framework-version-specific edge cases, sub-frame event races)? | 🟡 Partially answered | `LEARNINGS.md` Sprint 6A, Sprint 6B | Sprint 6A's null result is itself evidence on this question: a timing-based remount, however aggressive, did not reproduce `DETACHED_FROM_DOM` for this project's `Locator`-based interaction pattern, while real-world instances of that error trace to structurally different causes (reference-holding code, version-specific edge cases, dispatch-window races) that a timing-based mechanism doesn't model. Sprint 6B found a second, independent instance of the same pattern: `async_delay`'s conditional-DOM-mount design produces a message indistinguishable from `SELECTOR_NOT_FOUND`, not a genuine actionability failure — a mechanism's intended target and what it actually produces have now diverged twice, for two different mechanisms. Relevant to design decisions for any future Chaos App mechanism, not just these two |
| 9 | How often, in practice, would `LocatorResolutionCollector`'s inability to distinguish genuine selector drift from a conditionally-not-yet-mounted element actually cause PhoenixQA to "heal" a selector that was never broken? | 🔴 Open | Gap #14, `LEARNINGS.md` Sprint 6B (decision) | Named but not measured. `SelectorReplacement` is the decided default action for `FailureCategory.LOCATOR_RESOLUTION` regardless of which of the three causes actually applies — if a conditionally-mounted element (the `async_delay` case) is common in real target applications, this could mean PhoenixQA regularly proposes replacing selectors that were already correct, just slow to appear. Only answerable with real benchmark data (Sprint 7/8) or a deliberate DOM-poll-after-timeout experiment, neither built yet |

## Status legend
- 🔴 Open — no empirical answer yet, in either direction
- 🟡 Partially answered — some real evidence exists, but the question isn't fully resolved or hasn't been tested at the scale/rigor needed to trust the answer generally
- 🟢 Answered — a real experiment (not just an architectural decision) has produced a trustworthy answer

## Relationship to the benchmark runner (Sprint 7/8)

Several of these hypotheses (RH-1, RH-6, RH-7) are only properly
answerable once the Healing Benchmark Runner exists — they need a
real, repeatable measurement instrument, not a one-off manual test run,
to produce evidence anyone should actually trust. This is the same
discipline named in `LEARNINGS.md`'s "Process reflection" after Sprint
5: Sprint 8 is where the project commits to real STLC rigor specifically
*because* its output at that point is a measurement instrument, and a
sloppily-built benchmark would produce numbers nobody should believe —
undermining every hypothesis in this file that depends on it, not just
Gap #9's original heuristic-vs-LLM question.

## Where to read more
Search `LEARNINGS.md` for the sprint or gap referenced in each row above
to find the full reasoning, any experiments already run, and their
results.