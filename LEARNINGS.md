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

### Refinement: chaos levels as dict, not mechanism count

Initial pivot wrote levels as "LOW = 1 mechanism, CHAOS = 4 mechanisms" —
still implicitly coupled level to *count*. Corrected to an explicit dict:

```python
CHAOS_LEVELS = {
    "LOW": ["selector_rotation"],
    "MEDIUM": ["selector_rotation", "dom_mutation"],
    "HIGH": ["selector_rotation", "dom_mutation", "async_delay"],
    "CHAOS": ["selector_rotation", "dom_mutation", "async_delay", "shadow_dom"],
}
```

Reasoning: a level represents a **research scenario**, not a quantity of
chaos. The moment a 5th mechanism gets added (e.g. `a11y_noise`,
`locale_switch`, `feature_flags` — plausible future additions), a
count-based model breaks immediately. A dict model doesn't care how many
mechanisms exist; it only cares which ones belong to which named scenario.

### Refinement: mechanism realism ranking

Not all 4 mechanisms are equally representative of real-world failures.
Ranked by how often each actually causes test breakage in production
frontends:

| Mechanism         | Realism | Why |
|-------------------|---------|-----|
| DOM Mutation      | 10/10   | Any UI library refactor, wrapper changes, component migrations |
| Selector Rotation | 9/10    | Classic — renamed class/id/data-testid |
| Async Delay       | 8/10    | Lazy loading, animations, network-dependent rendering |
| Shadow DOM        | 5/10    | Real but narrower — mostly Web Components / LWC-style platforms |

Consequence: mechanisms are not equal in scope. DOM Mutation deserves the
most internal variants (wrap in extra element, change tag type, change
nesting depth, reorder siblings) since it's the highest-realism failure
mode. Shadow DOM can stay a simpler single-variant toggle — it's real, but
narrower in applicability.

Structural decision: each mechanism gets its own module under `chaos/`:
```
chaos/
├── selector_rotation.py
├── dom_mutation.py     ← gets the most internal complexity
├── async_delay.py
└── shadow_dom.py
```

### Refinement: Shadow DOM decoupled from CHAOS_LEVELS — becomes an orthogonal flag

Realism ranking above (5/10 vs 8-10/10 for the rest) raised a structural
question: should Shadow DOM be the "top" of a linear chaos progression, or
is it a fundamentally different *kind* of difficulty?

Decision: **orthogonal flag**, not a level. Shadow DOM isn't "more chaos" —
it's a different axis entirely (structural DOM access vs. selector/timing
volatility). Folding it into CHAOS_LEVELS as step 4 implied "harder than
async_delay," which isn't true — it's just *different*.

```python
CHAOS_LEVELS = {
    "LOW": ["selector_rotation"],
    "MEDIUM": ["selector_rotation", "dom_mutation"],
    "HIGH": ["selector_rotation", "dom_mutation", "async_delay"],
}

# Independent of chaos_level — combinable with any level
SHADOW_DOM_ENABLED = False  # env: SHADOW_DOM_ENABLED=true
```

This means a test run can be `HIGH + shadow_dom_enabled=true` — testing
"refactor + timing + structural access" as an explicit combination, rather
than forcing it to only exist at the top of one fixed ladder. Benchmark
runner in Sprint 7 gains a second dimension to report on: chaos_level ×
shadow_dom flag, instead of one flat list of 4 levels.

Consequence: `get_mechanisms_for_level()` returns only the level's list;
shadow DOM is checked separately via the flag, not included in that list.
`CHAOS` as a level name is retired — `HIGH` becomes the ceiling of the
linear progression, and shadow DOM rides on top of any level via the flag.



Beyond just `chaos_level`, tests and the future benchmark runner need a
single source of truth for "what mechanisms are actually active right now."

```python
active_mechanisms = get_mechanisms_for_level(chaos_level)
```

This closes the loop into Sprint 7 for free: the benchmark runner iterates
`CHAOS_LEVELS`, calls this helper, runs the suite, and already has the
mechanism list to log alongside the pass rate — no separate bookkeeping
needed.

---

### Verified: selector_rotation works as designed (manual browser check)

First real confirmation that code matches design, not just "compiles."

In browser DevTools, inspected `[id="chaos-username"]` across two page
reloads:
- Reload 1: `data-testid="username-h1fz"`
- Reload 2: `data-testid="username-rwp4"`

Confirms: suffix is stable within a single mount (doesn't change per
keystroke, thanks to `useMemo`), but rotates on every fresh mount. This is
exactly the failure mode the whole project exists to fix — a hardcoded
`[data-testid="username"]` locator (as used in `ChaosLoginPage.py`) will
never match anything on this app, because that exact attribute value never
exists standalone, only with a rotating suffix attached.

---

## TODO (future sprints)
- Sprint 1: implement CHAOS_LEVELS as dict (LOW/MEDIUM/HIGH, level → mechanism list), not count-based
- Sprint 1: shadow_dom is an independent flag (SHADOW_DOM_ENABLED), not part of CHAOS_LEVELS — combinable with any level
- Sprint 1: dom_mutation.py gets most internal variants (wrap/retag/nest/reorder) — highest realism mechanism
- Sprint 1: implement `get_mechanisms_for_level()` helper — returns level's mechanism list only; shadow_dom checked separately
- Sprint 1: parametrize chaos tests by `chaos_level` AND `shadow_dom_enabled` from the start — avoids rewriting tests in Sprint 7
- Sprint 2: decide on DOM snapshot strategy (full HTML vs targeted subtree)
- Sprint 3: prompt template for selector healing — include element role, aria, surrounding context
- Sprint 6: SQLite schema design — index by page_url + broken_selector for fast few-shot lookup
- Sprint 7 (renamed: "Healing Benchmark Runner" — name now matches what it actually does): iterate CHAOS_LEVELS × shadow_dom flag (two dimensions), call get_mechanisms_for_level(), run suite, log pass rate per combination. Few-shot self-training stays in scope as a sub-component, not the headline.