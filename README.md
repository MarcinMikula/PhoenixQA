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
- proposes a fix for human review (**Safe Mode**)
- applies the fix automatically and continues (**Autonomous Mode**)

Every decision is logged. Every logged decision improves future healing (**Self-Training Loop**).

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
"maybe later" — see `LEARNINGS.md` for the full reasoning.

---

## 🏗️ Architecture

```
Test Failure
    │
    ▼
Context Collector        ← DOM snapshot, screenshot, console logs, network
    │
    ▼
LLM Analyzer             ← Ollama (local) or Anthropic API
    │
    ├──► Safe Mode        ← Human reviews, accepts/rejects → Ground Truth
    │
    └──► Autonomous Mode  ← Auto-applies fix, re-runs test
              │
              ▼
        Healing History   ← SQLite log of all decisions
              │
              ▼
        Self-Training     ← Few-shot context for better future repairs
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

End goal (Sprint 7): run the full suite at every level, healing on vs off, and publish a measured effectiveness table — not just "it works," but "here's how much it helps."



```
PhoenixQA/
├── chaos_app/              # React/Vite — intentionally unstable test target
├── phoenix/
│   ├── collector/          # Context gathering on failure
│   ├── healing/            # Safe Mode + Autonomous Mode orchestration
│   ├── ai/                 # LLM provider abstraction (Ollama / Anthropic)
│   ├── training/           # Healing history + self-training loop
│   └── reporting/          # Allure Phoenix Healing Report
├── pages/                  # Page Objects for Chaos App (POM pattern)
├── tests/
│   ├── chaos/              # Tests running against Chaos App
│   ├── unit/
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
| Sprint 2 | Context Collector — `selector_not_found` only (DOM snapshot, weighted scoring) | ⏳ Planned  |
| Sprint 3 | LLM Analyzer — prompt engineering, structured JSON response, confidence score | ⏳ Planned  |
| Sprint 4 | Safe Mode — Human-in-the-loop, ground truth builder           | ⏳ Planned  |
| Sprint 5 | Autonomous Mode — auto-apply, pytest re-run loop, post-heal business validation | ⏳ Planned  |
| Sprint 6 | Failure type expansion — `detached_from_dom`, `not_visible`, `timeout_waiting` | ⏳ Planned  |
| Sprint 7 | Healing History — SQLite store, decision log, healing correctness definition | ⏳ Planned  |
| Sprint 8 | Healing Benchmark Runner — few-shot self-training, Safe vs Auto metrics | ⏳ Planned  |
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

# 5. Run tests against it (Healer lands in Sprint 4/5)
cd ..
pytest tests/chaos/ -m chaos
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