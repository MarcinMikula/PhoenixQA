# LEARNINGS.md

Conventions, decisions, and hard-won lessons from building PhoenixQA.
Carried across all repos in the ecosystem.

---

## Sprint 0

### Project structure
- Mirrors defect-pilot conventions: same folder layout, same `.env.example` pattern, same dual-provider AI abstraction
- `config/settings.py` is the single source of truth — no scattered `os.getenv()` calls
- `__init__.py` in every package — avoids mysterious import errors later

### AI Provider pattern
- `BaseProvider` (ABC) → `AnthropicProvider` / `OllamaProvider` → `provider_factory.get_provider(settings)`
- Switching providers = change one env var, zero code changes
- `HealingContext` and `HealingProposal` are dataclasses — structured, typed, LLM-agnostic

### BasePage healing hooks
- `healing=False` by default — opt-in per call, not opt-out
- Healing wired at method level (`click`, `fill`) not test level — transparent to test authors
- `NotImplementedError` stubs are intentional — better than silent no-ops

### Chaos App decision
- Must be built in-house — public sites too stable, rate-limited, or auth-walled
- React/Vite chosen for ecosystem familiarity and easy DOM manipulation
- Chaos levels: LOW / MEDIUM / HIGH / CHAOS — configurable, deterministic enough to write tests against

---

## Sprint 1 (pre-coding pivot)

### Pivot: Chaos App reframed as a Benchmark Environment

Originally planned as "React app with 4 randomized chaos mechanisms." Community
feedback (GitHub comment review) pushed this further — and the pivot is worth
recording because it changes both the architecture and the value proposition
of the whole project.

**Before:** 4 chaos mechanisms, CHAOS level = "all 4 at once," no stated
methodology for *why* each level exists.

**After:** Each level isolates a variable and answers a specific research
question. This turns Chaos App from "randomized weirdness" into a controlled
experiment — directly reusing risk-based testing thinking (same instinct as
ISTQB risk analysis: isolate one variable, observe one failure mode).

| Level  | Mechanisms (cumulative)                          | Research question |
|--------|---------------------------------------------------|--------------------|
| LOW    | selector rotation                                  | Does the test survive a selector rename? |
| MEDIUM | + DOM structure mutation                           | Does the test survive a UI refactor? |
| HIGH   | + async delay                                      | Does the test survive a refactor + timing issues? |
| CHAOS  | + shadow DOM                                       | Can the healer find the element regardless of implementation? |

**Key correction:** the 4th mechanism — DOM structure mutation (e.g. wrapping
`<button>` in an extra `<div>`, or `<form>` in a `<section>`) — had been
mentioned in architecture diagrams but was missing from the explicit level
breakdown. This is one of the most common real-world causes of brittle XPath
failures, so it's promoted from "one of four mechanisms" to its own dedicated
level (MEDIUM), since it represents a fundamentally different failure mode
than selector renaming.

### Pivot: project framed as a benchmark, not just a framework

End goal of Sprint 7 is no longer just "self-training loop exists." The
target deliverable is a **measurable effectiveness report**:

| Chaos Level | Tests | Pass Before Heal | Pass After Heal |
|-------------|-------|-------------------|-------------------|
| LOW         | 100   | ~72%              | ~98%              |
| MEDIUM      | 100   | ~51%              | ~95%              |
| HIGH        | 100   | ~29%              | ~90%              |
| CHAOS       | 100   | ~11%              | ~82%              |

(Numbers above are illustrative targets, not real data yet — first real run
happens once Healer ships in Sprint 4/5.)

This reframes the whole repo: not "Playwright + a sample app" (the most common
shape of QA portfolio repos), but a **Self-Healing Test Framework Benchmark
Environment** — closer to an R&D measurement tool than a tutorial project.
Sprint 7 scope grows accordingly: needs a benchmark runner that executes the
full suite per chaos level, with healing on/off, and aggregates results into
this table.

### Decision: why isolate variables per level instead of randomizing everything

Considered just exposing all 4 mechanisms as independent toggles with no
"levels" concept. Rejected — without ordered levels, a failed test gives no
information about *which* failure mode broke it. Levels give us a built-in
experiment design for free.

---

## TODO (future sprints)
- Sprint 1: DOM structure mutation engine needs to be a first-class mechanism, not a minor toggle — see pivot above
- Sprint 2: decide on DOM snapshot strategy (full HTML vs targeted subtree)
- Sprint 3: prompt template for selector healing — include element role, aria, surrounding context
- Sprint 6: SQLite schema design — index by page_url + broken_selector for fast few-shot lookup
- Sprint 7: benchmark runner — execute full suite per chaos level (healing on/off), aggregate into Pass Before/After Heal table