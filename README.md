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
- applies the fix automatically within a confidence/budget policy and continues (**Autonomous Mode** — in progress)

Every Safe Mode decision is logged today. Once Healing History (Sprint 7) lands, that log becomes the basis for a self-training loop that improves future healing (Sprint 8) — not yet built, but the logging that feeds it already is.

### Scope: where this starts, and where it's going

"Test fails even though the app is fine" has more than one root cause.
Real-world experience (Salesforce Lightning, enterprise SPAs) shows the
**most common** failure isn't actually a renamed selector — it's timing:
an element gets detached from the DOM mid-action because the framework
re-rendered, or a spinner disappears before the frontend has actually
finished updating.

PhoenixQA classifies failures into four types, but builds them in phases
rather than all at once:

| Failure type | Status |
|---|---|
| `selector_not_found` — classic renamed/rotated selector | 🚧 Building first (Sprint 2-5) |
| `detached_from_dom` — framework re-render mid-action | 🔜 Required, not yet built |
| `not_visible` — element exists but hidden/blocked | 🔜 Required, not yet built |
| `timeout_waiting` — never reaches an actionable state | 🔜 Required, not yet built |

Why phase it: better to prove the full pipeline (collect → analyze → heal
→ validate) end-to-end on one well-understood failure type first, then
extend to the others with real lessons learned — rather than build four
shallow strategies at once. The other three are committed scope, not a
"maybe later" — see `LEARNINGS.md` for the full reasoning, or
[`docs/gaps.md`](docs/gaps.md) for a quick-scan status table of every
open architectural question.

---

## 🏗️ Architecture

```
Test Failure
    │
    ▼
Context Collector        ← DOM snapshot, weighted semantic scoring, shadow DOM piercing
    │
    ▼
LLM Analyzer             ← Ollama (local) or Anthropic API → structured JSON proposal
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

**Controlling the chaos level:**

```bash
# chaos_app/.env
VITE_CHAOS_LEVEL=HIGH            # LOW | MEDIUM | HIGH
VITE_SHADOW_DOM_ENABLED=true     # true | false — independent of level
```

Edit `chaos_app/.env`, then restart `npm run dev`. The "Active chaos config" panel at the top of the running app confirms which mechanisms are live — no guessing required.

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
│   └── future-ideas.md
├── chaos_app/                # React/Vite — intentionally unstable test target
│   └── src/chaos/            # selectorRotation, domMutation, asyncDelay, shadowDom
├── phoenix/
│   ├── collector/            # failure_classifier, context_collector (weighted semantic scoring)
│   ├── healing/              # healer, safe_mode, decision_logger, autonomous_mode
│   ├── ai/                   # base_provider, ollama_provider, anthropic_provider,
│   │                         # prompt_templates, response_parser, provider_factory
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

| Sprint   | Focus                                                         | Status     |
|----------|---------------------------------------------------------------|------------|
| Sprint 0 | Repo scaffold, config, AI provider stubs                      | ✅ Done     |
| Sprint 1 | Chaos App — React/Vite, selector rotation, DOM mutation, async delay, Shadow DOM | ✅ Done     |
| Sprint 2 | Context Collector — `selector_not_found` only (DOM snapshot, weighted scoring) | ✅ Done     |
| Sprint 3 | LLM Analyzer — prompt engineering, structured JSON response, confidence score | ✅ Done     |
| Sprint 4 | Safe Mode — Human-in-the-loop terminal review, JSON-lines decision log | ✅ Done     |
| Sprint 5 | Autonomous Mode — stop conditions (attempts/tokens/time budget), confidence policy gate, distinct exception types | ⏳ In progress |
| Sprint 6 | Failure type expansion — `detached_from_dom`, `not_visible`, `timeout_waiting` | ⏳ Planned  |
| Sprint 7 | Healing History — SQLite store, decision log, healing correctness definition | ⏳ Planned  |
| Sprint 8 | Healing Benchmark Runner — Heuristic provider baseline, few-shot self-training, Safe vs Auto metrics | ⏳ Planned  |
| Sprint 9 | Allure Phoenix Report, CI/CD, demo GIF                        | ⏳ Planned  |

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
# Run tests against it — Safe Mode is live (Sprint 4)
# -s is REQUIRED: Safe Mode prompts for accept/reject via input(),
# and pytest swallows stdin/stdout without -s — the prompt never
# reaches the terminal and the run just hangs with no explanation.
pytest tests/chaos/ -m chaos -s
```

---

## 🎬 Demo

*(Parked until Sprint 5+ — once the Healer is actually catching and fixing failures, this section gets real screenshots/GIFs of a test failing on a rotated selector, healing, and going green. Not worth showing a static form screenshot before there's something to demonstrate.)*

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