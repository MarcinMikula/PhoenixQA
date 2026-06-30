# PhoenixQA — Test Strategy

This is a test strategy for **PhoenixQA itself** — the self-healing
framework as a product — not for Chaos App (which is the deliberately
unstable target PhoenixQA tests against; its own correctness is covered
incidentally by the same suite described here).

This is a **living document**: each section states the plan and the
current actual state side by side, with links into `LEARNINGS.md` for
the reasoning behind specific decisions. Updated as sprints progress, not
written once and frozen.

## Why this document exists

Most AI-healing side projects stop at "I have code and some unit tests."
This document exists to show a different level of thinking: quality
considered across the full stack — correctness of individual functions,
correct integration between components, and measurable effectiveness of
the framework as a whole, not just "it compiles and the demo works."

---

## 1. Unit tests

**Scope:** pure logic, no live browser, no live LLM — parsers, budget
tracking, classifiers, loggers. Fast, deterministic, run on every commit.

**Plan:** every module with non-trivial logic (anything beyond simple
plumbing) gets dedicated unit tests, written to cover both the happy
path and the specific edge cases that real LLM/Playwright output has
actually produced (not just hypothetical ones).

**Current state: 44 tests, all passing.**

| Module under test | File | What's covered |
|---|---|---|
| Selector tokenization | `test_context_collector.py` | Rotation suffix stripping, attribute selector parsing, id/class shapes |
| Failure classification | `test_context_collector.py` | `SELECTOR_NOT_FOUND` detection for both `click()` and `fill()` message shapes (the fill()-shaped gap was a real bug, see `LEARNINGS.md` Sprint 4) |
| LLM response parsing | `test_response_parser.py` | Clean JSON, markdown-fenced JSON, stray text around JSON, truncated JSON, missing fields, confidence clamping/coercion |
| Decision logging | `test_decision_logger.py` | JSON Lines format, append behavior, mode labeling (caught hardcoded to "safe", see `LEARNINGS.md` Sprint 5), enriched fields (provider/tokens/timing/attempt) |
| Budget/policy enforcement | `test_autonomous_policy.py` | Total-vs-per-selector attempt limits, token limits, `None`-safe token handling, policy configurability |
| Healer orchestration | `test_healer.py` | Safe Mode auto-reject on empty proposals, Autonomous Mode confidence gate, budget-exceeded blocking the LLM call entirely, provider exceptions still consuming budget |
| Provider selection | `test_provider_factory.py` | Correct provider returned per `AI_PROVIDER` setting, error on unknown provider |

**Notable pattern across this suite:** several of these tests exist
specifically *because* writing them surfaced a real bug before it
reached a live run (the rotation-suffix regex stripping real words like
"form"; the `fill()` vs `click()` message-shape gap; the hardcoded log
mode). This is tracked deliberately in `LEARNINGS.md` as evidence that
the unit layer is pulling real weight, not just padding a test count.

**Known gap:** `Healer`/`safe_mode.py` interaction with a real
Playwright `Page` and a real Ollama call is *not* unit tested — by
design, since that requires the integration layer below.

---

## 2. Integration tests

**Scope:** real components talking to each other — Playwright driving a
real (or realistic) page, `Healer` actually calling `ContextCollector`
and a real LLM provider, with the full pipeline wired together. Slower
than unit tests, still automatable, not yet requiring the full Chaos App
UI.

**Plan:** verify the seams between components work correctly in
isolation from the "does the chaos mechanism itself work" question —
e.g. does `ContextCollector` correctly extract a landmark from a real
Playwright page object, does `Healer` correctly route to Safe vs
Autonomous based on `Settings`, does a real (not mocked) `OllamaProvider`
round-trip correctly through `parse_healing_response`.

**Current state: not yet built as a distinct layer.** What exists today
(`tests/chaos/test_chaos_login.py`) is closer to end-to-end (see below)
than integration — it exercises the full stack against the real running
Chaos App rather than isolating component seams. The `tests/integration/`
directory exists (scaffolded since Sprint 0) but is currently empty.

**Why not yet:** the manual end-to-end runs against Chaos App (Sprint
4/5) have so far been a more efficient way to surface real bugs than
writing isolated integration tests would have been at this stage of the
project — every bug found live (truncated JSON, model default mismatch,
classifier message-shape gap, log mode bug) was found through full
end-to-end runs, not narrower integration scenarios. Revisit once the
pipeline is stable enough that narrower, faster integration tests would
catch regressions before a full e2e run is needed to find them.

---

## 3. End-to-end tests

**Scope:** the full real stack — real Chromium via Playwright, real
running Chaos App (React/Vite dev server), real local LLM (Ollama). No
mocks anywhere. This is where the project's actual claims get tested
against reality, not against a simulation of reality.

**Plan:** `tests/chaos/` exercises realistic user flows (login,
including a deliberately invalid-credentials path) against Chaos App
with `healing=True` engaged, across both Safe Mode and Autonomous Mode,
across multiple chaos levels once Sprint 6+ broadens failure-type
coverage.

**Current state: manually run, repeatedly, both modes confirmed working
live.**

- Safe Mode: confirmed end-to-end (Sprint 4) — terminal review prompt
  fires correctly, full context displayed, accept/reject both exercised,
  decisions logged.
- Autonomous Mode: confirmed end-to-end (Sprint 5) — zero terminal
  prompts, high-confidence proposals auto-applied, zero/low-confidence
  proposals auto-rejected, budget tracking and the three distinct
  exception types all observed firing correctly in real runs.
- Known, deliberately out-of-scope failure mode: `is_visible()`/
  `get_text()` have no healing path (see `docs/known-limitations.md`) —
  e2e runs have repeatedly and correctly demonstrated this boundary
  holding, not breaking unexpectedly.

**Known gap:** these runs are currently manual (`pytest tests/chaos/ -m
chaos -s`, watched and responded to by a human), not yet wired into CI.
Sprint 9 (CI/CD) is where this becomes automated — Autonomous Mode runs
require no human interaction and are the natural candidate for a CI gate
once `tests/chaos/` covers more than the login flow.

---

## 4. Regression benchmark (healing effectiveness)

**Scope:** not "does the code run without crashing" but "how often does
healing actually work, and does that hold steady or degrade as the
codebase changes." This is the layer most AI-healing demo projects skip
entirely.

**Plan:** the Healing Benchmark Runner (Sprint 8) executes the test
suite at every `CHAOS_LEVEL` (LOW/MEDIUM/HIGH) × Shadow DOM flag,
comparing **No Healer / Heuristic Healer / LLM Healer**, producing a
Pass Before/After Heal table per configuration — see `README.md`'s
Chaos Levels section and `docs/gaps.md` Gap #9 for the full reasoning on
why the heuristic baseline matters.

**Current state: not yet built — explicitly scoped to Sprint 8, not
before.** Sequencing reasoning (per `LEARNINGS.md`): prove the pipeline
end-to-end on one failure type first (done, Sprint 2-5), expand failure
type coverage (Sprint 6), only then build the measurement instrument
once there's a stable, multi-dimensional thing worth measuring.

**Important note on this category's own rigor** (see `LEARNINGS.md`
"Process reflection" and `docs/future-ideas.md`): Sprint 8 is
specifically where this project commits to applying real STLC discipline
— test strategy, entry/exit criteria, and validation of the benchmark's
own measurement validity — rather than treating the benchmark runner as
"just more code." The credibility of the entire Gap #9 narrative depends
on this category being done rigorously, not informally.

---

## 5. Non-functional tests

**Scope:** properties of the system that aren't "did the right answer
come back" but "did it come back within acceptable bounds, and does the
system behave sanely under adverse conditions." For an LLM-backed
framework specifically, this means budget discipline and resilience to
imperfect model output.

**Plan:**
- **Time budgets** — `max_time_per_heal_ms` enforced and verified (unit
  tests + live runs confirm `HealLifecycleTimer` measures the full
  collect+analyze+apply+retry span, not just the LLM call).
- **Token budgets** — `max_input_tokens`/`max_output_tokens` enforced
  (unit tests confirm independent tripping from attempt count; live runs
  confirm real token numbers are captured from Ollama's response).
- **Resilience to malformed LLM output** — this has turned out to be the
  single most exercised non-functional property in the project so far.
  Truncated JSON, markdown-fenced JSON, stray text, missing fields, and
  models echoing the broken selector back as their own "fix" have all
  been observed in real runs and are explicitly covered by
  `response_parser.py`'s defensive parsing and `Healer`'s
  zero-confidence auto-reject logic.
- **Infrastructure failure isolation** — confirmed live (`LEARNINGS.md`
  Sprint 4): stopping Chaos App entirely produces a clean, fast
  `ERR_CONNECTION_REFUSED` with the Healer never invoked at all, rather
  than a confusing failure deep inside the healing pipeline.

**Current state: substantially covered, mostly through real-world
discovery rather than designed-in-advance test cases** — which is itself
worth noting honestly (see `LEARNINGS.md` "Process reflection"): most of
this category's coverage came from live runs surfacing real LLM behavior
quirks, then being retroactively protected with unit tests, rather than
being anticipated up front. Reasonable for a project this size and
stage; worth tightening (e.g. deliberately fuzzing malformed LLM
responses rather than only covering observed ones) once Sprint 6-8 give
more failure-type surface area to test against.

**Explicitly not yet covered:** cost-at-scale behavior (what happens
across a large test suite with many concurrent healing attempts), and
provider-switching behavior (Ollama → Anthropic mid-session) — both
realistic future scope, not currently planned for any specific sprint.

---

## Summary table

| Layer | Status | Test count / evidence |
|---|---|---|
| Unit | ✅ Substantial | 44 tests, all passing |
| Integration | 🔴 Not yet built as distinct layer | `tests/integration/` scaffolded, empty |
| End-to-end | 🟡 Manual, both modes confirmed | 2+ live runs each, real bugs found and fixed |
| Regression benchmark | 🔴 Scoped to Sprint 8 | Not started — deliberately sequenced |
| Non-functional | 🟡 Substantially covered, reactively | Token/time budgets enforced; malformed-LLM resilience battle-tested live |

## Where to read more

- `LEARNINGS.md` — full chronological reasoning behind every decision
  referenced above, including the actual bugs found at each layer
- `docs/gaps.md` — open architectural questions, several of which
  intersect with this strategy (Gap #1 healing correctness, Gap #9
  baseline comparison)
- `docs/known-limitations.md` — scope boundaries this strategy
  deliberately doesn't try to paper over
