# 🔥 PhoenixQA

> Self-healing test automation framework for fragile frontends.
> When a selector breaks, PhoenixQA doesn't crash — it heals.

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![Playwright](https://img.shields.io/badge/Playwright-latest-green)](https://playwright.dev)
[![AI](https://img.shields.io/badge/AI-Ollama%20%7C%20Anthropic-purple)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🧠 What is this?

Frontend tests break constantly — not because the feature is broken, but because the page underneath it changed.
A class was renamed. A `data-testid` rotated. A wrapper `<div>` appeared around a button after a refactor. A component moved into a Shadow DOM boundary.

**PhoenixQA** intercepts those failures, feeds the context to an LLM, and either:
- proposes a fix for human review (**Safe Mode** — live)
- applies the fix automatically within a confidence/budget policy and continues (**Autonomous Mode** — live)

Every decision — human-reviewed or autonomous — is logged today, including which provider made the call, how many tokens it cost, and how long it took. Once Healing History (Sprint 7) lands, that log becomes the basis for a self-training loop that improves future healing (Sprint 8) — not yet built, but the logging that feeds it already is.

### Scope: where this starts, and where it's going

"Test fails even though the app is fine" has more than one root cause.
PhoenixQA classifies failures into four types, but builds them in phases
rather than all at once:

| Failure type | Status |
|---|---|
| `selector_not_found` — classic renamed/rotated selector | ✅ Live (Sprint 2-5) |
| `detached_from_dom` — framework re-render mid-action | 🔬 Investigated (Sprint 6A) — no reproduction found for `Locator`-based automation across four escalating attempts; deprioritized based on current evidence, not proven impossible — see `docs/gaps.md` Gap #4 |
| `not_visible` — element exists but hidden/blocked | 🚧 Modeled as `FailureCategory.ACTIONABILITY` + `ActionabilityReason.VISIBLE` — decided, not yet implemented; see below |
| `timeout_waiting` — never reaches an actionable state | 🚧 Superseded by the `FailureCategory.ACTIONABILITY` model (covers `enabled`/`editable`/`stable`/`receives_events` too) — decided, not yet implemented; see below |

Why phase it: better to prove the full pipeline (collect → analyze → heal
→ validate) end-to-end on one well-understood failure type first, then
extend to the others with real lessons learned — rather than build four
shallow strategies at once. See `LEARNINGS.md` for the full reasoning, or
[`docs/gaps.md`](docs/gaps.md) for a quick-scan status table of every
open architectural question.

**Note on `detached_from_dom`:** the original working assumption (based
on direct Selenium/Salesforce Lightning experience) was that framework
re-render-mid-action failures would be the dominant real-world case for
PhoenixQA to handle. Sprint 6A tested that assumption directly — a real
reproduction mechanism (`componentRemount.jsx`) was built and run across
four escalating configurations, ending with a deterministic,
zero-timing-luck trigger. The consistent finding: no observable
`DETACHED_FROM_DOM` failure, at any setting, for this project's specific
interaction pattern. Research into Playwright's own documentation and
issue tracker offers a likely explanation, not just a coincidence —
`Locator`-based actions (all `BasePage` ever uses; never `ElementHandle`)
are documented to retry automatically on mid-action detachment, which
would plausibly absorb much of the failure class Selenium-style
automation is vulnerable to. This is deliberately framed as evidence
supporting a deprioritization, not proof that the failure type doesn't
exist — see `LEARNINGS.md` "Sprint 6A conclusion" for the precise scope
of the claim, the full hypothesis → experiment → finding → decision
trail, sources, and what it means for the project's remaining scope.

**Note on `not_visible`/`timeout_waiting`:** before picking one of these
as the redirected target, a set of small diagnostic experiments checked
whether Playwright's own error messages can actually tell them apart —
`timeout_waiting`'s definition ("never reached an actionable state") is
close to a superset of `not_visible`'s. They can't, in the way the
original four-way `FailureType` split assumed. Real production logs plus
targeted live captures show Playwright's model is genuinely two-stage:
first "did the locator resolve at all" (a bare
`waiting for locator(...)` message, identical for `click()` and `fill()`,
means no), and only if it resolved, one of five distinct actionability
reasons (`visible`, `enabled`, `editable`, `stable`, `receives events`).
A flat choice between `not_visible` and `timeout_waiting` as separate
top-level types would have inherited the same ambiguity the classifier
already had for `selector_not_found` before Sprint 4's fix.

The decided replacement: `FailureCategory` (`LOCATOR_RESOLUTION` /
`ACTIONABILITY` / a dormant `REFERENCE` for the `detached_from_dom`
family) plus `ActionabilityReason` for the five concrete reasons above.
`LOCATOR_RESOLUTION`, deliberately not `SELECTOR` — an unresolved
locator has more than one plausible real cause (genuine selector drift,
an element that's conditionally not yet mounted, the app being in an
unexpected state), which Playwright's own message can't distinguish;
naming the category after "selector" would have presupposed the
diagnosis the evidence argued against. This is a decided architecture,
not yet implemented in code — see `LEARNINGS.md` "Sprint 6B (decision)"
and `docs/gaps.md` Gap #5/#12 for the full model, and Gap #13/#14 for
the two limits this decision explicitly does not resolve (the model's
dependence on Playwright's unversioned diagnostic text, and
`LocatorResolutionCollector`'s continued inability to tell apart *why*
a locator never resolved).

**Important framing shift for the remaining failure types (Gap #12):**
for `selector_not_found`, the selector itself is what's broken, and the
fix is a replacement selector. For the remaining failure types the
selector may be perfectly correct — what actually failed is the
in-flight ACTION (e.g. a click against an element that isn't yet
actionable, or never becomes actionable in time). PhoenixQA treats
`selector_not_found` as the special case where "recover the action" happens
to mean "propose a new selector" — the other failure types recover the
action a different way (retry with a wait, dismiss an overlay, scroll
into view, etc.). See `docs/gaps.md` Gap #12 and `LEARNINGS.md` Sprint 6.

**How this project approaches quality as a whole** — not just unit
tests on the framework's own code, but a layered strategy covering
integration, end-to-end behavior against a real LLM, regression
benchmarking of healing effectiveness, and non-functional resilience to
malformed model output — is laid out in
[`docs/testing-strategy.md`](docs/testing-strategy.md).

**The open empirical questions driving the project's direction** — does
an LLM meaningfully outperform a cheap heuristic, which failure types
actually justify LLM-based healing, is model confidence a reliable
proxy for correctness, and others — are collected in one place in
[`docs/research_hypotheses.md`](docs/research_hypotheses.md), separate
from `docs/gaps.md`'s architectural TODOs: a gap is something to build,
a hypothesis is something to find out.

---

## 🏗️ Architecture

```
Test Failure
    │
    ▼
Failure Classifier        ← FailureCategory (locator_resolution, actionability, reference)
    │                          + ActionabilityReason (5 values) — decided, not yet implemented;
    │                          today's live code still uses the flat FailureType enum
    │
    ▼
Context Collector          ← one collector per FailureCategory (target architecture):
    │                          locator_resolution_collector.py (DOM snapshot, weighted scoring)
    │                          — today's selector_collector.py, live, pending rename
    │                          actionability_collector.py        (planned, all 5 reasons)
    │                          reference_collector.py             (dormant, no active plan)
    ▼
LLM Analyzer               ← Ollama (local) or Anthropic API → structured HealingAction
    │                          SelectorReplacement — live today (currently keyed off
    │                          FailureType.SELECTOR_NOT_FOUND, target: locator_resolution)
    │                          ActionabilityStrategy (actionability, 5 reasons) — decided, not yet implemented
    │                          RetryStrategy (reference, dormant) — declared only
    │
    ├──► Safe Mode        ← Human reviews full context, accepts/rejects → Ground Truth
    │
    └──► Autonomous Mode  ← Confidence gate + budget check, auto-applies fix, retries
              │
              ▼
        Healing History   ← SQLite log of all decisions (Sprint 7)
              │
              ▼
        Self-Training     ← Few-shot context for better future repairs (Sprint 8)

Note: PhoenixQA recovers the ABILITY to perform an action after a
failure — it does not judge whether the resulting behavior was
business-correct (e.g. "did login actually succeed"). That judgment
stays with the test's own assertions, same as it always has. See
docs/gaps.md Gap #11 for why this boundary is deliberate.
```

Autonomous Mode raises one of three distinct exception types depending on *why* it didn't heal — `HealingRejectedError` (bad/low-confidence proposal), `HealingLimitExceededError` (budget exhausted), `HealingFailedError` (provider/API crashed) — so a CI failure report says exactly what happened, not just "healing didn't work."

**Current implementation status:** the `Context Collector → LLM Analyzer → HealingAction` split above is the target architecture for the next phase of work. As of today, `ContextCollector` is still a single class, `prompt_templates.py` is still one module, and providers still return `HealingProposal` (the `selector_not_found`-only shape) — the polymorphic collector/prompt structure and the `HealingAction` hierarchy are decided but not yet implemented. See [`docs/known-limitations.md`](docs/known-limitations.md) for the precise current-vs-planned boundary.

---

## 🧪 Chaos Levels — a benchmark, not just randomness

Chaos App isn't randomized weirdness — each level isolates one variable and answers a specific research question. This is closer to a controlled experiment than a typical "Playwright + sample app" portfolio repo.

| Level  | Mechanisms (cumulative)              | Research question |
|--------|----------------------------------------|--------------------|
| LOW    | selector rotation                       | Does the test survive a selector rename? |
| MEDIUM | + DOM structure mutation                | Does the test survive a UI refactor? |
| HIGH   | + async delay                           | Does the test survive a refactor + timing issues? |

**Shadow DOM is a separate, independent flag** (`SHADOW_DOM_ENABLED`), not a 4th level — it's a different *kind* of difficulty (structural DOM access), combinable with any level above (e.g. `HIGH + Shadow DOM` tests refactor + timing + structural access at once).

Mechanisms ranked by real-world realism (most enterprise frontends break this way most often):

| Mechanism         | Realism | Why |
|--------------------|---------|-----|
| DOM Mutation       | 10/10   | UI library upgrades, wrapper changes, component migrations |
| Selector Rotation  | 9/10    | Classic — renamed class/id/data-testid |
| Async Delay        | 8/10    | Lazy loading, animations, network-dependent rendering |
| Shadow DOM         | 5/10    | Real, but narrower — mostly Web Components / LWC-style platforms |

A 5th, independent mechanism, **component remount / detach-mid-action** (`componentRemount.jsx`, `COMPONENT_REMOUNT_ENABLED`), was built in Sprint 6A specifically to give `detached_from_dom` something real to classify against. It's implemented and verified live, but — see the Scope section above — did not reproduce the target failure against `Locator`-based interactions even under a deterministic, zero-timing-randomness trigger. It remains in the codebase as a verified research tool, not as an active target for the next healing strategy.

**Controlling the chaos level:**

```bash
# chaos_app/.env
VITE_CHAOS_LEVEL=HIGH            # LOW | MEDIUM | HIGH
VITE_SHADOW_DOM_ENABLED=true     # true | false — independent of level
VITE_COMPONENT_REMOUNT_ENABLED=false   # true | false — independent of level, see note above
```

Edit `chaos_app/.env`, then restart `npm run dev`. The "Active chaos config" panel at the top of the running app confirms which mechanisms are live — no guessing required.

**Mechanism overrides (development/verification only, never for the official benchmark):** each core mechanism (`selector_rotation`, `dom_mutation`, `async_delay`) can be forced on/off independently of the active level via `VITE_OVERRIDE_SELECTOR_ROTATION` / `VITE_OVERRIDE_DOM_MUTATION` / `VITE_OVERRIDE_ASYNC_DELAY`, useful for isolating one mechanism's effect during development without inventing a new named chaos level for every combination. `CHAOS_LEVELS`'s three named scenarios remain the only thing the eventual benchmark runner configures via plain `CHAOS_LEVEL`.

End goal (Sprint 8 — Healing Benchmark Runner): run the full suite at every level, comparing **No Healer vs. Heuristic Healer vs. LLM Healer** — not just "it works," but "here's exactly how much the LLM adds over a cheap fuzzy-match baseline, and where."

| Chaos Level | No Healer | Heuristic Healer | LLM Healer |
|---|---|---|---|
| LOW    | ~72% | ?% | ~98% |
| MEDIUM | ~51% | ?% | ~95% |
| HIGH   | ~29% | ?% | ~90% |

The middle column is the actual experiment — a simple fuzzy/Levenshtein selector matcher (zero LLM calls, same provider interface as Anthropic/Ollama) might already solve a surprising fraction of cases. Without this baseline, "90% healed" doesn't prove the LLM was necessary.

**Autonomous Mode has hard stop conditions from day one** (`max_attempts_total`, token budget, `max_time_per_heal`) — no infinite LLM retry loops in CI, by design, not as a later hardening pass. Budget is tracked in tokens and elapsed time, never in currency — model pricing changes over time, token counts don't. See `docs/architecture-decisions.md` for the full reasoning.

```
PhoenixQA/
├── LEARNINGS.md             # chronological journal — problem → analysis → decision → test → conclusion
├── docs/                    # thematic indexes (fast lookup by topic, not by sprint)
│   ├── gaps.md              # all numbered architectural gaps, status at a glance
│   ├── architecture-decisions.md
│   ├── known-limitations.md
│   ├── future-ideas.md
│   ├── testing-strategy.md  # unit/integration/e2e/regression-benchmark/non-functional plan + actual state
│   └── research_hypotheses.md  # open empirical questions the project is trying to answer, not just architectural gaps to fix
├── chaos_app/                # React/Vite — intentionally unstable test target
│   └── src/chaos/            # selectorRotation, domMutation, asyncDelay, shadowDom, componentRemount (Sprint 6A)
├── phoenix/
│   ├── collector/            # failure_classifier, context_collector (router, planned) + collectors/ (per-FailureType, planned)
│   ├── healing/               # healer, safe_mode, decision_logger, autonomous_mode
│   ├── ai/                   # base_provider, ollama_provider, anthropic_provider,
│   │                         # prompts/ (per-FailureType, planned), response_parser, provider_factory
│   ├── training/             # Healing history (Sprint 7)
│   └── reporting/            # Allure Phoenix Healing Report (Sprint 9)
├── pages/                    # Page Objects for Chaos App (POM pattern)
├── tests/
│   ├── chaos/                # tests running against Chaos App
│   ├── unit/                 # tokenizer, classifier, parser, logger, healer tests
│   └── integration/
└── config/
```

---

## 🔒 Privacy-first AI design

| Provider    | When to use                                      |
|-------------|--------------------------------------------------|
| `ollama`    | Air-gapped / NDA environments, local LLM         |
| `anthropic` | Cloud projects, best quality healing suggestions |

Switch via single env variable. No code changes.

---

## 🗺️ Roadmap

| Sprint    | Focus                                                         | Status     |
|-----------|-----------------------------------------------------------------|------------|
| Sprint 0  | Repo scaffold, config, AI provider stubs                      | ✅ Done     |
| Sprint 1  | Chaos App — React/Vite, selector rotation, DOM mutation, async delay, Shadow DOM | ✅ Done     |
| Sprint 2  | Context Collector — `selector_not_found` only (DOM snapshot, weighted scoring) | ✅ Done     |
| Sprint 3  | LLM Analyzer — prompt engineering, structured JSON response, confidence score | ✅ Done     |
| Sprint 4  | Safe Mode — Human-in-the-loop terminal review, JSON-lines decision log | ✅ Done     |
| Sprint 5  | Autonomous Mode — stop conditions (attempts/tokens/time budget), confidence policy gate, distinct exception types | ✅ Done     |
| Sprint 6  | Failure type expansion — architecture decided (action-recovery reframing, polymorphic collector, split prompts, `HealingAction` hierarchy); target failure type redirected after Sprint 6A findings | 🚧 In progress |
| Sprint 6A | `componentRemount.jsx` (TIMEOUT + MOUSEDOWN triggers) + classifier extended to recognize `DETACHED_FROM_DOM` | ✅ Done — controlled experiment (4 escalating configurations) found no reproduction against `Locator`-based automation; a finding about Playwright's architecture, not a mechanism gap. See `LEARNINGS.md` "Sprint 6A conclusion" |
| Sprint 6B-D | `DetachedFromDomCollector` / `detached_prompt.py` / `RetryStrategy` end-to-end, as originally scoped | ⏸️ Redirected — `FailureCategory`/`ActionabilityReason` model decided (see `LEARNINGS.md` "Sprint 6B (decision)"), `parse_playwright_call_log()` rewrite is the next concrete implementation step, not yet started |
| Sprint 7  | Healing History — SQLite store, decision log, healing correctness definition | ⏳ Planned  |
| Sprint 8  | Healing Benchmark Runner — Heuristic provider baseline, few-shot self-training, Safe vs Auto metrics | ⏳ Planned  |
| Sprint 9  | Allure Phoenix Report, CI/CD, demo GIF                        | ⏳ Planned  |

**Sprint 6 architectural decisions made before any code was written** (full reasoning in `LEARNINGS.md`, indexed in `docs/gaps.md` Gap #12 and `docs/architecture-decisions.md`):
1. The non-`selector_not_found` failure types are reframed as **action recovery**, not selector replacement — there may be nothing wrong with the selector itself.
2. `ContextCollector` becomes a router over one `BaseContextCollector` subclass per `FailureType`, replacing the current if/elif ladder.
3. The prompt layer splits the same way — one prompt module per `FailureType`, since "find a selector" and "should this action be retried, and after what wait" are different cognitive tasks for the model.
4. `HealingProposal` is retired as the universal provider return type, replaced by a `HealingAction` hierarchy — `SelectorReplacement` (`locator_resolution`), one merged `ActionabilityStrategy` parameterized by reason + recovery kind (`actionability`, superseding the originally-declared separate `WaitStrategy`/`VisibilityStrategy`), and a dormant `RetryStrategy` (`reference`) — a required, blocking refactor touching `Healer`, `safe_mode.py`, `decision_logger.py`, and `response_parser.py`. See `LEARNINGS.md` "Sprint 6B (decision)" for the finalized shape.

These four decisions remain sound regardless of which specific failure type gets the next vertical slice — they were designed to generalize, not built around `detached_from_dom` specifically. What changed after Sprint 6A is only the answer to "which failure type comes next": a controlled experiment against Playwright's `Locator` API (see the Scope section above and `LEARNINGS.md` "Sprint 6A conclusion" for the full hypothesis → experiment → finding → decision trail) found that `detached_from_dom` isn't a high-value target for this architecture right now. A follow-up round of diagnostics (Sprint 6B, see the Scope section's `not_visible`/`timeout_waiting` note above) then found that picking one of the two remaining types outright isn't the right next move either — Playwright's own model splits failures into "did the locator resolve" and, if so, one of five actionability reasons, which the current flat enum doesn't capture. The concrete shape of the fix is an open, upcoming decision.

---

## 🚀 Quickstart

```bash
# 1. Clone
git clone https://github.com/MarcinMikula/PhoenixQA.git
cd PhoenixQA

# 2. Install Python deps
pip install -r requirements.txt
playwright install chromium

# 3. Configure
cp .env.example .env
# Edit .env — choose AI provider, chaos level

# 4. Run the Chaos App (test target)
cd chaos_app
npm install
cp .env.example .env
npm run dev
# → http://localhost:5173

# 5. In a SEPARATE terminal (npm run dev keeps step 4's terminal busy):
cd ..
# Run tests against it — both Safe Mode (Sprint 4) and Autonomous Mode
# (Sprint 5) are live. Switch via .env: HEALING_MODE=safe | autonomous
#
# -s is REQUIRED for Safe Mode: it prompts for accept/reject via input(),
# and pytest swallows stdin/stdout without -s — the prompt never
# reaches the terminal and the run just hangs with no explanation.
# Autonomous Mode doesn't need -s (no prompts), but it doesn't hurt either.
pytest tests/chaos/ -m chaos -s
```

---

## 🎬 Demo

Healing is confirmed working live as of Sprint 5 — Safe Mode and Autonomous Mode have both been run end-to-end against the real Chaos App and a local LLM, with selectors successfully healed and retried in place.

The actual demo artifact, though, is parked until Sprint 9: rather than a pile of terminal screenshots, the plan is a single **Allure Healing Dashboard** (success rate, healing timeline, confidence distribution, top repaired selectors, failure reasons, budget usage, provider comparison) — built once Sprint 6-8 (failure type expansion, healing history, benchmark runner) produce real data for it to render. See `docs/future-ideas.md` for the reasoning.

---

## 🤝 Part of the QA Ecosystem

PhoenixQA is one piece of a larger AI-powered QA toolkit:

| Repo | Role |
|------|------|
| [qa-automation-framework](https://github.com/MarcinMikula/qa-automation-framework) | POM/SOM skeleton — PhoenixQA heals its selectors |
| [defect-pilot](https://github.com/MarcinMikula/defect-pilot) | AI bug reproduction & retest agent |
| [llm-qa-toolkit](https://github.com/MarcinMikula/llm-qa-toolkit) | LLM-as-judge test framework for AI chatbots |

---

## 📄 License

MIT