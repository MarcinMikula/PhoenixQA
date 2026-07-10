# LEARNINGS.md

Conventions, decisions, and hard-won lessons from building PhoenixQA.
Carried across all repos in the ecosystem.

**This file is the project's chronological journal** — problem → analysis
→ decision → implementation → test → conclusion, sprint by sprint. It's
intentionally kept this way even as it grows long, because the sequence
itself is part of the value: it shows the actual thinking process, not
just a list of outcomes.

**For fast lookup by topic instead of by sprint**, see the thematic
indexes in `docs/`:
- [`docs/gaps.md`](docs/gaps.md) — all numbered architectural gaps, status at a glance
- [`docs/architecture-decisions.md`](docs/architecture-decisions.md) — key decisions, grouped by area
- [`docs/known-limitations.md`](docs/known-limitations.md) — what's deliberately incomplete or fragile right now
- [`docs/future-ideas.md`](docs/future-ideas.md) — brainstormed possibilities, deliberately deferred
- [`docs/testing-strategy.md`](docs/testing-strategy.md) — quality strategy for PhoenixQA itself: unit/integration/e2e/regression-benchmark/non-functional, plan vs actual state
- [`docs/research_hypotheses.md`](docs/research_hypotheses.md) — the project's open empirical questions in one place (does an LLM outperform a heuristic, is confidence correlated with correctness, etc.), each pointing back to where it was raised and where it stands

Each index entry is a short summary + pointer back here — full reasoning
always lives in this file, never duplicated.

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

## Sprint 2 (pre-coding) — Major scope decision: FailureType classification

### Gap analysis before writing code

Before implementing Context Collector, four architectural gaps were
identified by reviewing the roadmap critically:

1. **No definition of "healing correctness"** — test passing after a fix
   ≠ fix is actually correct (e.g. LLM changes `[data-testid='save']` to
   `button`, test passes, but clicks the wrong button if multiple buttons
   exist). Affects Sprint 6 (Healing History schema) — must be resolved
   before that schema is designed, not before Sprint 2.
2. **No confidence score in the pipeline** — actually already planned:
   `HealingProposal.confidence: float` exists in `base_provider.py` since
   Sprint 0. Not a gap, just not yet implemented (lands in Sprint 3).
3. **No post-heal business-level validation** — "selector exists" ≠
   "business action succeeded" (click(save) should also verify a toast
   appeared / record persisted / URL changed, not just that the click
   didn't throw). Naturally belongs to Sprint 4/5 (Safe/Autonomous Mode) —
   can't be built before there's a fix to validate.
4. **Scope question: "selector healer" vs "UI automation healer"** — see
   below. This is the one gap that required a decision BEFORE Sprint 2
   code, because it changes the shape of `HealingContext` itself.

Gaps 1-3 are tracked but don't block Sprint 2 — they're naturally
sequenced into later sprints by the existing roadmap. Gap 4 required
immediate resolution.

### Decision: FailureType classification — selector vs timing vs visibility vs detachment

Real-world input (13+ years across telco/banking, recent hands-on
Salesforce Lightning experience): the MOST COMMON real enterprise SPA
failure is NOT a renamed selector — it's **timing-related**:

- **Detached from DOM**: element is found, but Lightning re-renders the
  component between `find` and `click` — the element reference becomes
  stale mid-action. Different failure mechanism than "never existed."
- **Spinner/render race**: network call finishes, but frontend hasn't
  finished re-rendering yet — element exists but isn't actionable.
- **Not visible**: element is in the DOM but hidden behind an overlay,
  spinner, or not-yet-expanded section.

This means "selector healer" (current architecture — Context Collector
designed in this sprint) and "UI automation healer" (README's broader
framing) are NOT competing scopes to choose between — they're different
**categories of the same higher-level problem**: "test fails even though
the application is working correctly." Conflating them would have made
Sprint 2's Context Collector too narrow to be useful on the failure types
that actually dominate in production.

**Resolution — phased, not all-at-once:**

```python
class FailureType(Enum):
    SELECTOR_NOT_FOUND = "selector_not_found"   # element never existed with this selector
    DETACHED_FROM_DOM = "detached_from_dom"      # existed, framework removed it mid-action
    NOT_VISIBLE = "not_visible"                  # in DOM, but hidden (spinner, overlay)
    TIMEOUT_WAITING = "timeout_waiting"           # never reached an actionable state
```

Context Collector gets a classification step BEFORE context gathering:

```python
def collect_failure_context(page, error, original_code, broken_selector=None):
    failure_type = classify_playwright_error(error)
    # routes to a different context-gathering strategy per type —
    # semantic scoring (designed earlier this sprint) only applies to
    # SELECTOR_NOT_FOUND; other types need timing/render-state data instead
```

**Sprint 2 scope (decided): SELECTOR_NOT_FOUND only.** The semantic-scoring
algorithm designed earlier this sprint is fully built and verified
end-to-end (Collector → LLM Analyzer → Healer) for this one failure type
first. Reasoning: better to prove the full Sprint 2→3→4 pipeline works
correctly on one well-understood failure type than to spread effort thin
across four loosely-built ones.

**Explicitly NOT abandoned — tracked as required, not optional:**
DETACHED_FROM_DOM, NOT_VISIBLE, and TIMEOUT_WAITING handling MUST be built
later (their own sprint or folded into Sprint 3). This is the single
biggest scope expansion in the project's history — README and roadmap
both need to reflect it, since "self-healing for selectors" and
"self-healing for UI automation broadly" are different promises to make
to a reader.

**Consequence for Chaos App:** none of the current 4 chaos mechanisms
simulate DETACHED_FROM_DOM or render-race conditions. A future chaos
mechanism (e.g. "component remounts N ms after initial render" or
"element removed and re-added during an in-flight click") will likely be
needed once this expanded scope is actually implemented.



Considered two options for what Context Collector hands to the LLM:

**Full page HTML** — rejected for real enterprise targets (SAP, Salesforce,
CBS-style platforms). These generate enormous DOM trees (Lightning
components, Fiori re-renders). Full HTML is expensive in tokens, slow, and
— worse — dilutes signal. The failure has one specific cause in one specific
place; burying it in the whole page makes the LLM's job harder, not easier.

**Targeted subtree** — selected. But not naive "go N levels up from the
broken selector." Real strategy needs:
1. Don't search FOR the broken element (that's the thing that's missing) —
   search for the nearest STABLE reference point: a parent with a real
   `id`, ARIA role, or another `data-testid` likely to survive a refactor.
2. Walk UP toward landmarks, not down into children — the context that
   explains "what is this element" usually lives in a parent (form label,
   section heading), not in what the broken element itself contains.
3. MUST pierce Shadow DOM boundaries explicitly. `outerHTML` does not
   cross into a shadow root — for elements inside `<phoenix-chaos-shadow-host>`,
   the collector has to walk into `.shadowRoot` directly or it captures an
   empty host tag with nothing useful inside.
4. Dual limit: max depth AND max character count, whichever hits first.
   "Walk 3 levels up" sometimes lands on a single useful section, sometimes
   lands on `<div id="app-root">` with 500 children (the whole layout) —
   needs both guards, not just one.

### Refinement: scoring must start from the selector name, not DOM position

Initial subtree strategy ("walk up to nearest visible form/section") was
caught as flawed before any code was written — worth recording why, since
it's a subtle trap. With multiple forms on a page (e.g. a login form AND a
newsletter signup in a header), "first visible form" can land on something
completely unrelated to the broken selector. It would have looked like it
worked on Chaos App (single form per view) and silently produced garbage
context on any real multi-section enterprise page.

Corrected approach: start from the only real signal we actually have —
the broken selector's name itself.

1. **Tokenize the broken selector.** `[data-testid='username-ab12']` →
   `["username"]`. Random rotation suffixes (short alphanumeric tails like
   `ab12`, `rwp4`) must be filtered out — they're noise from our own
   `selectorRotation.js`, not signal.
2. **Score every element in the DOM** against those tokens, checking
   `data-testid`, `aria-label`, `name`, `placeholder`, `id`, `textContent`.
3. **Weighted scoring, not flat +1 per match.** An intentional test hook
   (`data-testid`) is a much stronger signal than an incidental text match
   (`textContent`):

   | Source        | Weight |
   |----------------|--------|
   | data-testid    | 5      |
   | aria-label     | 4      |
   | name           | 4      |
   | placeholder    | 3      |
   | id             | 2      |
   | textContent    | 1      |

   Example: `<input data-testid="username-rwp4">` scores 5; a coincidental
   `<label>Username</label>` scores 1 — a 5x gap instead of a tie, which
   flat scoring would have produced.
4. **Ties are kept, not arbitrarily broken.** If multiple elements score
   equally, all of them get included as candidates rather than picking one
   at random — the LLM gets real ambiguity to reason about instead of a
   silently wrong guess.
5. **Only THEN walk up** via `closest('form, section, [role]')` — from the
   best-scoring candidate, not from an arbitrary DOM position.
6. **Shadow DOM check moves to the END**, not the start. Originally planned
   to scan for all shadow hosts upfront "just in case." Corrected: score
   candidates first (now knowing what we're looking for), then check
   whether the winning candidate lives inside a shadow root — more
   precise, cheaper in tokens, since `document.querySelectorAll` never
   sees inside shadow roots anyway and a separate shadow-piercing pass is
   needed regardless.

### Known fragility, deliberately not fixed in Sprint 2: outerHTML re-matching

Scoring runs in one `page.evaluate()` call and returns `outerHTML` strings.
A second `page.evaluate()` then re-finds the "same" element by matching
that string — but identical elements (e.g. repeated table rows, two
buttons both rendering "Save") collide. Whichever matches first wins,
which may not be the one that was actually scored.

Not blocking Sprint 2 — Chaos App's current components don't yet trigger
this collision in practice. But explicitly tracked, since it's the kind of
bug that fails silently (looks like it works, quietly hands the LLM
context for the wrong element) rather than loudly:

```python
# TODO Sprint 3:
# Re-finding elements via outerHTML string match is fragile — identical
# elements collide (e.g. repeated table rows). Replace with: keep the
# Playwright ElementHandle (or a unique DOM ancestor path) from the SAME
# evaluate() call that scored it, instead of re-querying a second time.
```



Brainstormed idea, deliberately NOT in scope for Sprint 2 — recording so it
isn't lost.

Idea: instead of only collecting context reactively when a test FAILS,
also snapshot the locator + its DOM context whenever a test PASSES. This
gives the Healer a historical "last known good" reference to diff against,
instead of reconstructing context from scratch at failure time only.

Why this is appealing: a diff-based signal ("this selector used to point
to the 2nd input inside `.chaos-form`; now no exact match exists, but
there's an `<input>` in the same structural position with a different
suffix — high-confidence match") is qualitatively stronger than guessing
purely from the DOM at failure time.

Why this is NOT happening now: it changes `BasePage` from "healing is
opt-in at failure" to "logging is always-on for every test run," even
ones that never need healing. It also means the history database grows
unboundedly without a retention strategy (e.g. "keep only latest known-good
snapshot per locator," not full history of every run).

Why this isn't wasted scope creep: this isn't a 4th independent system —
it's a natural extension of `history_store.py` (Sprint 6), which already
exists to store healing decisions. Adding "also store baseline snapshots
on green runs" is deepening that one component, not adding a new one.
Revisit when Sprint 6 is actually being built.

**Precise framing for future comparison** (added after follow-up discussion):
this isn't just "should we add baseline snapshotting" — it's a genuine
architectural fork worth measuring, not guessing about:

```
Approach A (current plan):  DOM → LLM → fix
Approach B (future option): historical fingerprint + current DOM → LLM → fix
```

The Healing Benchmark Runner (Sprint 7) is what makes this comparison real
instead of a hunch — once it exists, both approaches can be run through
the same Pass Before/After Heal table, per chaos level, and the question
becomes answerable with numbers: does the historical fingerprint produce
a measurably higher heal rate, or just more complexity for the same
outcome? Don't implement Approach B until Approach A has a benchmark
baseline to compare against.

---

### Major gap analysis: four architectural gaps identified before writing Sprint 2 code

Before implementing the Context Collector pseudo-code above, a deeper
review surfaced four gaps in the project's architecture. Recording all
four and how each was resolved or deferred — this is the most consequential
planning discussion so far, since one of the four gaps changes the shape
of `HealingContext` itself.

**Gap #1 — No formal definition of "healing correctness."**
Roadmap currently implicitly assumes: LLM proposes fix → test passes →
success. But "test passes" ≠ "fix is correct." Example: original selector
targeted a specific Save button; LLM widens it to a generic `button`
selector; test technically passes but now clicks the wrong element. Without
a definition of *correctness* (not just *pass rate*), all downstream
metrics (success rate, healing rate, benchmark results, self-training
signal) are measuring the wrong thing — could show "90% healed" while only
"30% actually correct."
Status: **not blocking Sprint 2.** Context Collector gathers data
regardless of how correctness gets defined later. But this MUST be
resolved before Sprint 6 (Healing History schema needs a place to record
correctness, not just pass/fail).

**Gap #2 — No confidence score in the LLM response structure.**
Safe Mode and Autonomous Mode both need a confidence signal to route
decisions (e.g. 95% → auto-apply, 60% → human review, 20% → reject).
Status: **already scaffolded.** `HealingProposal.confidence: float` exists
in `base_provider.py` since Sprint 0 — this isn't a missing gap, it's an
unimplemented field waiting for Sprint 3 (LLM Analyzer) to actually
populate it meaningfully.

**Gap #3 — No validation of business-level success after applying a fix.**
Current plan: apply fix → re-run → green. But "selector now resolves" is
not the same as "the intended action actually happened." Example: `click(save)`
succeeding at the DOM level doesn't confirm a toast appeared, a record was
saved, or the URL changed — i.e. selector existing ≠ business action
succeeding.
Status: **not blocking Sprint 2.** Logically can't be built before Sprint
4/5 (Safe/Autonomous Mode) exist to apply fixes in the first place — but
explicitly tracked as required scope for those sprints, not an afterthought.

**Gap #4 — Scope ambiguity: "selector healer" vs "UI automation healer."**
This was the one gap that DOES block Sprint 2, because it changes the
shape of `HealingContext` before any code gets written.

Architecture so far (Chaos App mechanisms, Context Collector pseudo-code)
implicitly assumes the failure mode is always "selector doesn't resolve."
But real enterprise SPAs (confirmed against direct Salesforce Lightning
experience) most commonly fail differently — not selector renaming, but
**timing**: an element is found, then detaches from the DOM mid-action
because the framework re-renders the component between `find` and `click`;
or a spinner disappears but the component hasn't finished re-rendering; or
a network call completes before the frontend finishes drawing the result.
These are categorically different failures (`StaleElementReference`-style,
not `TimeoutError`-on-locate-style) requiring different collected context
and a different LLM prompt — "propose a new selector" vs. "propose a
waiting/retry strategy" are different tasks.

**Resolution — staged scope, not a binary A/B choice:**

```python
from enum import Enum

class FailureType(Enum):
    SELECTOR_NOT_FOUND = "selector_not_found"   # element never existed with this selector
    DETACHED_FROM_DOM = "detached_from_dom"      # existed, framework removed it mid-action
    NOT_VISIBLE = "not_visible"                  # exists in DOM, but not visible (spinner/overlay)
    TIMEOUT_WAITING = "timeout_waiting"           # never reached an actionable state
```

Context Collector routes by failure type from the start:

```python
def collect_failure_context(page, error, original_code, broken_selector=None):
    failure_type = classify_playwright_error(error)
    if failure_type == FailureType.SELECTOR_NOT_FOUND:
        return collect_selector_context(...)   # the semantic-scoring approach above
    elif failure_type == FailureType.DETACHED_FROM_DOM:
        return collect_timing_context(...)      # NOT YET DESIGNED — different data needed
    elif failure_type == FailureType.NOT_VISIBLE:
        return collect_visibility_context(...)  # NOT YET DESIGNED
    # ...
```

**Decision: Sprint 2 implements ONLY `SELECTOR_NOT_FOUND` fully** (the
semantic-scoring pseudo-code already designed above). The `FailureType`
enum and routing function are built now so the architecture doesn't need
reshaping later, but `DETACHED_FROM_DOM` / `NOT_VISIBLE` / `TIMEOUT_WAITING`
branches are explicit `NotImplementedError` placeholders.

**This is a confirmed, MANDATORY future scope expansion, not an optional
nice-to-have** — direct production experience (Salesforce Lightning)
confirms timing/detachment failures are the most common real-world case,
more common than selector renaming. Reasoning for sequencing anyway:
verify the full Sprint 2→3→4 flow works end-to-end on one well-understood
failure type first, then extend to the others with working knowledge of
what the end-to-end pipeline actually needs — rather than designing three
failure-type pipelines simultaneously before any of them have been proven.

Practical consequence: Chaos App will eventually need a 5th mechanism
(or an extension to existing ones) that simulates re-render-mid-action /
detachment — `async_delay` alone doesn't currently simulate "element
existed, then got removed and replaced." This is new scope for the Chaos
App, not just for `phoenix/collector/`.

**Confirmed: deliberately deferred to Sprint 6, not built now.** Decision
reaffirmed in a direct follow-up ("ship one working slice end-to-end,
then expand") rather than building all failure-type mechanisms in
parallel before any of them are proven through the full pipeline.

Concrete spec for Sprint 6, so this isn't just a vague reminder:
- New file: `chaos_app/src/chaos/componentRemount.jsx` — wraps a target
  element; on interaction (or after a short delay), unmounts and
  re-mounts it as a genuinely new DOM node (not just a re-render — the
  old node must actually be replaced, mirroring what Lightning does)
  while keeping it visually identical, so the failure is purely structural
  / timing-based, not visually detectable.
- Also worth closing explicitly in Sprint 6: `asyncDelay.js` already
  produces an invisible→visible transition (via `useChaosDelay`), which
  incidentally covers part of `NOT_VISIBLE` — but this was never named as
  intentional coverage for that failure type. Sprint 6 should make this
  explicit (comment + LEARNINGS note) rather than leaving accidental
  overlap undocumented.
- `TicketList.jsx`'s three structurally-identical rows (`TCK-001/002/003`)
  already provide a ready-made test case for the Sprint 3 `outerHTML`
  collision TODO — no new Chaos App code needed for that specific gap.

### Gap #9 — missing baseline comparison (no-healer / heuristic / LLM)

Raised in follow-up discussion: the Healing Benchmark Runner (Sprint 7/8)
as currently scoped only measures "with healing vs without healing." It
does NOT answer the more important question: **was an LLM actually
necessary?** A simple heuristic (e.g. fuzzy string match / Levenshtein
distance between the old and new selector token, ignoring rotation
suffixes) might solve a large fraction of `selector_not_found` cases with
zero LLM cost or latency. Without this baseline, the project can show
"90% healed" without ever proving the LLM contributed anything beyond
what cheap string matching would have achieved.

This is not a nitpick — it's the difference between "built an LLM-based
self-healer" (sounds like AI-for-AI's-sake) and "measured exactly where
LLM reasoning adds value over heuristics, and where it doesn't" (a real
R&D conclusion, defensible in an interview).

**Resolution:** add a third provider implementing the existing
`BaseProvider` interface — `HeuristicProvider` — using simple fuzzy
matching, no LLM call at all. Because the provider abstraction already
exists (Sprint 0 decision), this costs nothing architecturally: heuristic
matching is just a third provider, not a separate system. Final benchmark
table gains a third column:

| Chaos Level | No Healer | Heuristic Healer | LLM Healer |
|---|---|---|---|
| LOW    | ~72% | ?% | ~98% |
| MEDIUM | ~51% | ?% | ~95% |
| HIGH   | ~29% | ?% | ~90% |

The unknown middle column is the actual experiment. Plausible (and equally
interesting) outcomes: heuristic matches LLM performance on LOW (simple
rotations) but falls off sharply on HIGH (structural DOM changes need real
reasoning) — or heuristic stays surprisingly competitive everywhere, which
would be an honest, valuable conclusion in its own right ("LLM isn't
strictly necessary for healing, but adds explainability heuristics can't").

Status: scoped into Sprint 7/8 (Healing Benchmark Runner), not Sprint 2.
`HeuristicProvider` needs its own file (`phoenix/ai/heuristic_provider.py`)
implementing `analyze_failure()` without ever calling an LLM API.

**Clarification (from follow-up discussion): the heuristic does NOT
depend on historical fingerprinting.** Easy to conflate these — both
involve "matching a selector to something" — but they anchor on different
things entirely:

- **Heuristic (Gap #9, usable now)** anchors on the PRESENT: the broken
  selector's own name (tokenized — same `tokenize_selector()` logic
  already built in Sprint 2, stripping the rotation suffix) compared
  against attributes of elements that exist in the CURRENT live DOM via
  fuzzy/Levenshtein matching. No history required. This is essentially a
  simplified, LLM-free version of what `context_collector.py`'s weighted
  scoring already does — same anchor, no model call at the end.
- **Historical fingerprint (Sprint 6 future consideration, see above)**
  anchors on the PAST: a snapshot of how the element looked the last time
  it was known to work, diffed against the current DOM.

Consequence: the Gap #9 benchmark (No Healer / Heuristic / LLM) is fully
buildable on what already exists from Sprint 0-4 — it does not need to
wait for Sprint 6. Fingerprinting, if pursued later, would be a fourth
column or a modifier on the existing two ("Heuristic + fingerprint", "LLM
+ fingerprint") — an enhancement to the experiment, not a precondition
for running it.

### Project philosophy note: HeuristicProvider is a control, not a product feature

Worth stating explicitly, because it changes how the Gap #9 benchmark
should be talked about and written up, not just how it's built.

`HeuristicProvider` is not "a cheaper alternative healing mode" sitting
alongside Ollama/Anthropic as a third option for users to pick. It exists
as an **experimental control** — the same role a placebo or baseline
plays in any real measurement. Its only job is to answer one question:
how much of the healing problem can be solved WITHOUT an LLM at all?

This reframes what the benchmark is actually for. Most AI-healing
projects report a single number: "the LLM healed 94% of failures." That
number alone says nothing about whether an LLM was the right tool for
the job — it could be 94% because the problem is genuinely hard and
needs real reasoning, or it could be 94% because most of these failures
are trivial string-matching cases that a 20-line regex would have solved
just as well.

With the control in place, the same result becomes: "a simple
tokenization + fuzzy-matching heuristic reached 81% on the same failure
set; the LLM reached 94%. The model's actual contribution was 13
percentage points." That's a fundamentally different — and more
credible — claim. It demonstrates the problem was actually
INVESTIGATED before reaching for an LLM, rather than assuming an LLM was
necessary because the project is about AI.

This is the difference between an "AI everywhere" project and one that
answers a real engineering question: where do deterministic heuristics
stop working, and where does language-model reasoning actually start
being necessary? The second framing is the one worth defending in an
interview — it shows judgment about WHEN to reach for an LLM, not just
the ability to wire one up.

Practical consequence for write-up (Sprint 7/8, README, any future
presentation of this project): always report the heuristic baseline
number ALONGSIDE the LLM number, never the LLM number alone. The gap
between them — not either number in isolation — is the actual finding.

### Gap #10 — missing stop conditions for Autonomous Mode

Raised in follow-up discussion: nothing in the current design prevents
infinite retry loops. Scenario: LLM fix #1 fails → LLM fix #2 fails → LLM
fix #3 fails → ... with no defined endpoint. In Autonomous Mode running
inside CI/CD, this isn't theoretical — it's a direct path to runaway API
cost and runtime, every single pipeline run, with no human in the loop to
notice and intervene.

**Resolution:** stop conditions are a BLOCKING requirement for Sprint 5
(Autonomous Mode), not a later hardening pass. Minimum set:
- `max_attempts` — hard cap on healing retries per failing test (e.g. 3)
- `max_cost_per_test` — token/API spend ceiling per single healing session
- `max_time_per_heal` — wall-clock timeout per healing attempt

Autonomous Mode must not ship — even as a Sprint 5 proof-of-concept —
without these three guards in place. This is unlike most other TODOs in
this file, which describe future refinements; this one describes a
precondition for Sprint 5 being considered "done" at all.

### Gap #5 — no failure classifier component (still open)

`FailureType` enum exists, and the Context Collector pseudo-code references
a `classify_playwright_error()` function — but that function has never
actually been designed. Right now there's a named intention
(`Failure -> Classifier -> Strategy`), not an architecture. Before Sprint 2
code is written, this needs at minimum: a mapping from Playwright exception
types/messages to `FailureType` values, and a decision on whether
classification can be done from the exception alone or needs a DOM probe
(e.g. checking if the element still exists at all vs. exists-but-hidden).
Tracked as a required Sprint 2 sub-task, not a separate future sprint —
the collector can't route by failure type without it.

### Gap #7 — no accounting for cost (tokens, storage, runtime)

Stop conditions (Gap #10, `max_cost_per_test`) touch this, but there's been
no broader reflection on prompt token budgets, DOM snapshot size limits
in storage (not just in the LLM context window), retention policy for
`history_store.py` (Sprint 6) — does old healing history get pruned, ever?
— or wall-clock runtime budget for a full benchmark run across all chaos
levels. Not blocking any current sprint, but should get a dedicated pass
once Sprint 6 (history) and Sprint 7/8 (benchmark) are actually being
built — premature to size these limits before real token/runtime numbers
exist from Sprint 3/4.

### Gap #8 — screenshot under-weighted vs DOM snapshot

`HealingProposal`/`HealingContext` (Sprint 0) already declares
`screenshot_path: Optional[str]`, but every Sprint 2 design discussion
since (semantic scoring, subtree extraction, shadow DOM piercing) has been
entirely DOM-first. The screenshot field exists on paper but has had zero
design attention — no decision on when it's actually useful (e.g. visual
layout bugs a DOM diff can't capture, like an element rendering off-screen
or behind an overlay) vs. when it's dead weight (most `selector_not_found`
cases are arguably fully explainable from DOM alone). Worth a deliberate
decision in Sprint 3 (LLM Analyzer) about whether multimodal input is
actually part of the v1 prompt or explicitly deferred — right now it's
neither decided nor implemented, just declared.

### Verified: Sprint 2 unit tests pass on both dev machines

`tokenize_selector` and `classify_playwright_error` confirmed working via
11 unit tests (8 new + 3 from Sprint 0), green both in the sandbox and on
Marcin's Windows machine. Caught a real bug during test-writing itself:
the rotation-suffix regex was stripping genuine 4-letter words (`form`,
`name`) because it matched on length alone — `.chaos-form` lost "form"
the same way `username-ab12` was meant to lose "ab12". Fixed by requiring
the suffix to mix letters AND digits (true base36 shape) before treating
it as rotation noise — pure-letter 4-char tokens now survive. This is
exactly the kind of bug that looks fine by inspection and only shows up
once a real word collides with the suffix-length heuristic.

### Known inefficiency, not optimized yet: multiple evaluate() calls per failure

`_collect_selector_context` calls `page.evaluate()` up to 4 times per
failure: once for light-DOM scoring, once for shadow-DOM scoring, and once
more per tied top-scoring candidate for landmark lookup. Each round-trip
has real cost (serialization, IPC to the browser process). Sprint 2
prioritized correctness of the scoring logic over this — premature to
optimize before Sprint 3/4 give real numbers on how often ties happen in
practice and how expensive this actually is end-to-end (ties to Gap #7,
cost accounting). Worth collapsing into fewer round-trips once there's
data to justify the refactor, not before.

## Sprint 3 (pre-coding)

### Decision: separate model for Sprint 3 verification, llava parked for later

`defect-pilot`'s `ai/ollama_provider.py` (httpx-based, `/api/generate`,
`stream: False`, `is_available()` health check via `/api/tags`) is the
convention PhoenixQA's `OllamaProvider` follows — confirmed by reading the
actual file rather than guessing the shape.

`defect-pilot` uses `llava` locally (vision-capable, good at analyzing bug
screenshots). PhoenixQA also has `llava:latest` pulled already. But `llava`
is vision-first and built on an older text architecture (Vicuna/Llama2-era)
— reliable structured JSON output is less certain than with newer
text-optimized models.

Decision: pull `llama3.2` specifically for Sprint 3 verification, rather
than debugging prompt/parsing architecture and model JSON-reliability as
one tangled variable. Same instinct as the CHAOS_LEVELS isolation
decision earlier — separate the variables, verify one thing at a time.
`llava` stays installed and gets revisited specifically for Gap #8
(screenshot / multimodal input) once that's actually being decided, not
before. `defect-pilot`'s `complete_with_images()` pattern (raw base64 in
the `images` field, no data URI prefix) is already a usable reference for
that future work.

### Verified: Sprint 3 components built and unit tested (no live Ollama needed yet)

Built `prompt_templates.py` (system + user prompt, SELECTOR_NOT_FOUND
only — see Gap #4), `response_parser.py` (defensive JSON extraction), and
`ollama_provider.py` (httpx-based, mirrors defect-pilot's convention
exactly: `/api/generate`, `stream: False`, `is_available()`-style health
check via `/api/tags`).

Caught a real bug while writing parser tests, same pattern as Sprint 2's
rotation-suffix regex bug: `_extract_json_text`'s bare-object regex
(`\{.*\}`) requires a closing brace, so a TRUNCATED response (model cut
off mid-generation — a realistic failure mode, not a contrived edge case)
never matched the regex at all. This produced a misleading "No JSON
object found" message instead of the more honest "JSON parse error" —
the model clearly tried to respond, it just didn't finish. Fixed by
adding a third fallback: if no complete `{...}` block matches, take
everything from the first `{` onward and let `json.loads()` produce a
real parse error. 10/10 parser unit tests pass; 21/21 total unit tests
pass project-wide.

Not yet tested: an actual live call to `OllamaProvider.analyze_failure()`
against running Ollama + llama3.2. That's the next concrete step — verify
the prompt actually produces usable selector proposals against real
Chaos App DOM context, not just that the parsing plumbing works on
hand-crafted sample strings.

## Sprint 4 — Safe Mode implementation

### Built: full Safe Mode pipeline, wired end-to-end

`BasePage.click()/fill()` now actually call `Healer.attempt_heal()` on a
Playwright timeout (when `healing=True`) instead of raising
`NotImplementedError` — this is the connection point that's been a stub
since Sprint 0. Flow confirmed in direct discussion and matches the
diagram: test fails → `ContextCollector` + LLM analyze → terminal shows
full context (old selector, error, proposal, confidence, reasoning) →
human accepts/rejects → on accept, selector is substituted and the
SAME action is retried in the SAME test step (not a test restart) → on
reject, the ORIGINAL Playwright error propagates so pytest reports the
real failure, not a healing-related one → decision logged either way.

New files: `phoenix/healing/safe_mode.py` (terminal review prompt),
`phoenix/healing/decision_logger.py` (JSON-lines log, NOT SQLite — see
below), `HealingRejectedError` in `healer.py` (lets `BasePage` distinguish
"human declined" from "healing crashed").

### Decision: Healer is lazily constructed in BasePage, not built in __init__

`BasePage.__init__` no longer eagerly creates a `Healer`. Most BasePage
instances in a typical test run never hit a failure path, so constructing
a provider + collector for every single page object would be wasted setup
cost. `_get_healer()` builds it on first actual use instead.

### Decision: ground truth logging — JSON Lines file, not SQLite, for Sprint 4

Confirmed in direct discussion: simple append-only log
(`healing_decisions.log`) now, full `history_store.py` SQLite schema
deferred to Sprint 6 — building the real schema before Gap #1 (healing
correctness definition) is resolved would mean guessing at structure
twice. Each log line captures the FULL decision context (selector, error,
proposal, confidence, reasoning, accept/reject), not just a pass/fail
flag — per direct discussion, the log needs to support a human tracing
back through "what was the diagnosis, was the fix right" after a test run
finishes, not just a binary outcome.

### IMPORTANT — pytest -s required for Safe Mode to work at all

`safe_mode.py` uses Python's `input()` to block and wait for the human's
accept/reject decision. Pytest captures stdout/stdin by default during
test execution — without the `-s` flag (`--capture=no`), the prompt never
reaches the terminal and the test just hangs with no visible explanation.

```bash
pytest tests/chaos/ -m chaos -s
```

This is exactly the kind of gotcha that wastes 20 minutes of confused
debugging on first run if it isn't written down loudly. Documented here
AND needs to land in README's Quickstart section once Sprint 4 testing
is verified end-to-end against real Chaos App + Ollama.

### Verified: 24/24 unit tests pass (3 new for decision_logger)

`decision_logger.py` is the only Sprint 4 piece testable without a live
browser page or a real Ollama call — pure file I/O, tested with pytest's
`tmp_path` fixture. `Healer`/`safe_mode.py` need a real Playwright page
and a real LLM round-trip, so they're exercised via manual end-to-end
testing against Chaos App, not unit tests. No bugs caught this time
(unlike Sprint 2's regex bug and Sprint 3's truncated-JSON bug) — the
logger's logic was simple enough that it passed clean on the first
write, which is itself worth noting as a contrast to the pattern in
earlier sprints.

**Not yet done — next concrete step:** an actual end-to-end run against
the real Chaos App + Ollama + llama3.2, with `pytest -s`, to see the
terminal review prompt fire on a real rotated selector and confirm the
full retry-in-place behavior actually works outside of unit-tested
pieces in isolation.

### First real end-to-end run — caught a bug unit tests couldn't catch

Ran `pytest tests/chaos/ -m chaos -s` against the real Chaos App for the
first time. Two environment setup issues hit first (both Windows/network
specific, not project bugs): `playwright install chromium` failed with
`UNABLE_TO_VERIFY_LEAF_SIGNATURE` (same corporate SSL-inspection pattern
as the earlier `npm install` issue) — resolved with
`$env:NODE_TLS_REJECT_UNAUTHORIZED="0"` for that one install command.

With the browser installed, the real bug surfaced: `classify_playwright_error`
returned `FailureType.UNKNOWN` instead of `SELECTOR_NOT_FOUND`, which sent
execution into the `NotImplementedError` branch reserved for Sprint 6
failure types — even though this WAS a Sprint 2 in-scope case.

Root cause: the classifier required both `"waiting for locator"` AND
`"to be visible"` in the exception message. That pattern matches
Playwright's `click()` timeout wording, but `fill()` — which is what
`ChaosLoginPage.login()` actually calls first — logs only
`"waiting for locator(...)"`, with no `"to be visible"` suffix, because
`fill()` waits for editability, not strict visibility. Every unit test
for the classifier (Sprint 2) had been written against click()-shaped
sample text, so this gap was invisible until a real `fill()` call hit it.

This is the clearest demonstration yet of why "unit tests pass" and "the
pipeline works end-to-end" are different claims — exactly Gap #1's
underlying concern (test passing ≠ correctness), just showing up one
layer earlier than expected, in the classifier rather than in healing
correctness itself.

Fix: loosened the condition to `"waiting for locator" in message` alone —
true for both click() and fill() timeout shapes, still narrow enough to
correctly return `UNKNOWN` for genuinely different message shapes (the
existing "unrecognized timeout shape" test still passes unchanged). Added
a dedicated regression test for the fill()-shaped message specifically,
so this exact gap can't silently reopen. 25/25 unit tests pass after the
fix.

**Practical lesson for future sprints:** classifier/parser logic written
against hand-crafted sample strings is necessary but not sufficient —
real Playwright/Ollama output has shapes we won't think to write samples
for until we see them. Worth running a real end-to-end pass earlier in
each future sprint, not just at the very end, to surface this category of
gap sooner.

### Second real bug from the same end-to-end run: default model mismatch

With the classifier fixed, the request reached `OllamaProvider.analyze_failure()`
and Ollama returned `404 Not Found` on `/api/generate`. Confirmed via a
manual `curl -Method POST` with `"model":"llama3.2"` that the endpoint and
Ollama itself were fine — the 404 was Ollama's response to being asked
for a model that isn't pulled, not a routing/connectivity problem.

Root cause: `Settings.ollama_model` defaulted to `"llama3.1"` (carried
over from before the Sprint 3 model-selection decision), and
`.env.example` still said `OLLAMA_MODEL=llama3.1` too — but `llama3.1` was
never pulled; the actual decision (see "Sprint 3 — Decision: separate
model" above) was `llama3.2`. Anyone whose local `.env` was copied before
that decision silently asks Ollama for a model that doesn't exist on
their machine, and gets a bare 404 with no indication of why.

Fix: corrected the default in both `config/settings.py` and
`.env.example` to `llama3.2`, matching the actual Sprint 3 decision.
Also added a `health_check()` call at the start of `analyze_failure()` —
previously `health_check()` existed but nothing ever called it before
attempting a real request, so this exact failure mode produced a generic
`httpx.HTTPStatusError` instead of the clear, actionable message
`health_check()` was already designed to give ("Run: ollama pull X").

**Practical lesson, reinforcing the one above:** two real bugs found in
one end-to-end run, neither catchable by unit tests, both in the
"plumbing between components" rather than in any single component's
internal logic. This is exactly why Sprint 4 budgeted for a live run
rather than declaring the sprint done on unit tests alone.

### Third iteration: prompt rewrite fixed the actual healing quality problem

Root cause confirmed via temporary diagnostic logging of the full prompt
sent to Ollama (added and removed in `ollama_provider.py` — not meant to
stay in the codebase, just a one-time diagnosis tool). The DOM snapshot
itself was correct and complete — `ContextCollector` was never the
problem. `llama3.2`, given a working snapshot, still either:
(a) echoed the broken selector back as its own "fix" with false high
confidence, or (b) got cut off mid-generation on a verbose `reasoning`
field, producing unparseable truncated JSON.

Original `SYSTEM_PROMPT` described the task at a conceptual level
("propose the most likely replacement") without a mechanical procedure.
Rewrote it as an explicit numbered algorithm: extract the base name from
the broken selector, scan the HTML's attributes, match base names while
expecting a DIFFERENT suffix, copy the actual found value verbatim, and
an explicit rule stating that an identical broken/proposed selector is
itself an error condition. Added one few-shot example showing the exact
input→output shape expected. Also shortened the required `reasoning`
field to "one short sentence" to reduce truncation risk.

Result, confirmed on the next real run: `llama3.2` correctly returned
`username-gffw` and `username-kqt9` — actual rotated values copied
verbatim from the provided HTML — with valid, complete JSON and
reasoning that names the specific attribute found, not a generic
restatement of the task. Both were manually rejected during this run
only to test the reject path, not because the proposals were wrong.

**Sprint 4 conclusion:** the full Safe Mode pipeline — failure →
classify → collect context → LLM analyze → terminal review → log — is
confirmed working end-to-end against a real browser and a real local
LLM. Not yet confirmed: the ACCEPT path (selector substitution + retry
producing an actual green test) — next concrete step before considering
Sprint 4 fully closed.

### Confirmed: ACCEPT path works — username and password healing succeeded twice

Ran the full suite with `y` on every prompt. `username` and `password`
fields healed correctly in BOTH tests — proposed selector substituted,
`fill()` retried, value entered successfully. This is the core Sprint 4
claim confirmed for real: a test action that failed on a rotated selector
can be transparently repaired and continue in the same step.

### Bug found and fixed: empty/zero-confidence proposals must auto-reject, not prompt

One `click()` healing attempt hit a truncated-JSON parse failure (same
known failure mode as before — verbose `reasoning` field, model cut off
mid-generation). `response_parser.py`'s fallback correctly produced
`proposed_selector=""`, `confidence=0.0`. But `Healer.attempt_heal()`
still asked "Accept this fix?" for that empty result. Answering `y` out
of habit (a real, easy-to-make mistake during fast iteration through many
prompts) sent `""` straight into `page.locator("")`, producing a CSS
parse error completely unrelated to the original selector failure —
confusing if you didn't already know why.

Root cause: there was no early-exit check for "this proposal has nothing
in it." A confidence of exactly 0.0 combined with an empty selector is
not a judgment call for a human to weigh — it's the parser's own signal
that nothing usable came back, and asking for "review" of nothing is
itself the bug.

Fix: `Healer.attempt_heal()` now checks `if not proposal.proposed_selector
or proposal.confidence <= 0.0` BEFORE calling `request_human_review()`,
auto-rejecting with a clear message and logging the decision the same as
any other rejection — no silent skip, just no pointless prompt. Added
`tests/unit/test_healer.py` with two tests (mocked provider/collector,
no live page needed): one confirming the empty case auto-rejects without
ever reaching `request_human_review()` (proven by the test completing at
all rather than hanging on `input()`), and one confirming a genuinely
low-but-nonzero-confidence proposal still correctly reaches the human —
the fix only catches the specific empty/zero case, not "low confidence"
in general. 28/28 unit tests pass.

### Scope gap found, not fixed: is_visible()/get_text() never had healing=True at all

`test_invalid_credentials` healed `username`, `password`, AND `btn-login`
successfully (form submission worked), but the test still failed — its
final assertion `is_visible(MSG_ERROR)` returned `False`. `MSG_ERROR` is
a stable selector string in `ChaosLoginPage`, but `is_visible()` and
`get_text()` in `BasePage` never had a `healing` parameter at all —only
`click()` and `fill()` do. The error message element rotates its
data-testid like everything else in Chaos App, so a stable selector
checking for it will fail just as surely as a stable `fill()` selector
would — there was simply never a healing path available for read-only
assertions.

This is a deliberate Sprint 0 scope boundary surfacing for the first
time, not a new bug — `BasePage`'s healing hooks were designed around
"actions that DO something" (click, fill), not "assertions that CHECK
something." Whether read-only assertions should ALSO be healable is a
real open question: arguably yes (a flaky assertion selector is just as
real a maintenance cost as a flaky action selector), but it also raises
a new question Safe Mode hasn't had to answer yet — what does "healing"
even mean for an assertion that returns a boolean rather than performing
an action? Worth deciding deliberately in a future sprint rather than
bolting on `healing=True` to `is_visible()` reactively.

### Verified: infrastructure failures correctly bypass healing entirely

Curiosity-driven experiment (per direct discussion: "z ciekawości sprawdzę
co się stanie jak wyłączę naszą Chaos App, taka symulacja server error"):
ran the test suite with Chaos App's dev server stopped. Result: clean,
fast failure (6.36s) — `Page.goto: net::ERR_CONNECTION_REFUSED`, raised
directly from `login_page.open()` → `navigate()`, with the Healer never
invoked at all.

This confirms the healing=True boundary is in the right place: `navigate()`
never had a healing parameter, because "the server isn't there" and "the
selector changed" are fundamentally different failure classes — no
selector-repair logic, however good, can fix a server that isn't running.
No wasted Ollama round-trip was attempted on a problem an LLM can't solve.
Good evidence the architecture's scope boundaries (healing=True only on
click()/fill(), never on navigate()) hold up under a failure mode that
wasn't explicitly tested for, not just the ones Sprint 2-4 were built
around.

## Sprint 5 (pre-coding) — Autonomous Mode design

Before writing any code, a detailed design discussion resolved five
open questions from Gap #10 and surfaced one genuinely new gap (#11).

### Decision: max_attempts is total-per-session, with per-selector tracking

Considered `max_attempts_per_selector` alone — rejected. A login flow
with 4 fields, each healing independently with its own counter of 3,
could legally execute 4×3=12 healing attempts in a single test run,
which is not what "max 3 attempts" was meant to mean from a budget
perspective. What actually matters business-wise is: how many times do
I let AI intervene in THIS ONE RUN.

Resolved with two-tier tracking:
```python
HealingSession:
    attempts_total       # hard cap across the whole session

HealingAttempt:
    selector
    attempt_number_for_selector   # tracked per-selector too, for diagnostics
```
`max_attempts_total` (e.g. 5) is the actual stop condition. Per-selector
attempt numbers are still recorded — useful diagnostic signal ("this one
selector is unusually problematic") for Sprint 6 history, but not itself
a limit.

### Decision: budget in tokens/time, never in currency

Strong position, fully adopted: never hardcode a dollar cost. Model
pricing changes (cited example: Anthropic's per-token price changing
year over year) — code that encodes "$15/1M tokens" becomes wrong
silently when pricing changes, while "8000 input tokens" is a fact that
never goes stale. The provider's only job is to report neutral facts:
```python
ProviderResult:
    input_tokens
    output_tokens
    elapsed_ms
```
A separate `HealingBudget` (tokens_used, time_used, attempts_used)
consumes these reports and enforces limits. Users who want a dollar
figure can compute it themselves from token counts at whatever the
current price happens to be — that conversion does not belong in this
codebase.

### Decision: max_time_per_heal wraps the full lifecycle, not just the LLM call

CI doesn't care that the LLM responded in 2s if retry logic then took
90s — the number that matters is the full `collect() + analyze() +
apply() + retry()` lifecycle, measured as one wall-clock span. Timing
only the LLM call would under-report the actual cost of a healing
attempt to anyone reading a CI report.

### Decision: three distinct exception types, not one

Originally only `HealingRejectedError` existed (Sprint 4, for human
rejection). Confirmed these are three genuinely different failure
classes, not variations of one:

- `HealingRejectedError` — the LLM responded, but the fix was bad /
  declined (existing, Sprint 4)
- `HealingLimitExceededError` — the system stopped healing because a
  budget (attempts/tokens/time) was exhausted, NEW for Sprint 5
- `HealingFailedError` — the LLM/API call itself raised an exception
  (network error, malformed request, etc.), NEW for Sprint 5

Rationale: a CI report reading "FAILED: limit exceeded" tells a very
different story than "FAILED: bad proposal" or "FAILED: provider
crashed" — collapsing them into one exception type would make failure
reports far less actionable.

### Decision: confidence threshold is a configurable policy, not a hardcoded constant

Rejected hardcoding `confidence >= 0.75` directly in `Healer`. Instead:
```python
AutonomousPolicy:
    min_confidence
    max_attempts
    max_tokens
    max_time
```
This cleanly separates Safe Mode (confidence is informational, the
human decides) from Autonomous Mode (confidence is a hard gate, the
system decides) — both modes share the same underlying
collect→analyze pipeline, differing only in policy.

### Gap #11 (NEW) — confidence ≠ correctness

The single most important point raised in this discussion, and a
genuinely new gap, not a restatement of Gap #1 or #3.

An LLM can report `confidence: 0.99` while pointing at the WRONG
element. The model being confident does not make it correct. Concrete
failure scenario: a `username` field heal picks the wrong input
(perhaps a search box with a similarly-rotated `data-testid`), `fill()`
succeeds at the Playwright level with zero exceptions, but the
subsequent login attempt fails for reasons that look like a completely
unrelated bug 20 actions later. The healing was technically
"successful" and substantively wrong.

### Resolved: where does correctness validation belong? (Option A vs B vs C)

Three options were weighed for where to catch this:

**Option A — pass a `validate_success` callback into `click()`/`fill()`.**
Rejected. This makes `Healer` aware of business logic — "did the login
succeed," "is the basket total correct" — which is a different
responsibility than "recover the ability to perform this action."
Within a year this style of API tends to accumulate
`validate=..., policy=..., hooks=..., telemetry=...` parameters on every
single action call, and `Healer` quietly becomes a second testing
framework living inside a self-healing framework. A clear SRP violation.

**Option B — Healer does its job, business correctness stays entirely
in the test's own assertions** (the status quo, unchanged). Drawback:
when a wrong-but-technically-successful heal happens, the eventual
`AssertionError` can land many steps later, far from the actual
`click()`/`fill()` that was the real problem — a real diagnosis cost.

**Option C — Healer validates only TECHNICAL success criteria,
Playwright-equivalent in spirit**: did the exception clear, did the
retried action execute without raising, does the locator still resolve,
is the page still open. Explicitly NOT business criteria like "was the
right button clicked" or "did the order get saved." Direct analogy:
Playwright's own `click()` never checks "was the order saved" either —
only "did the click happen."

**Decision: Option B, with Option C's technical-criteria framing
applied to whatever IS checked.** Reasoning, stated as a layered
responsibility model:
- Playwright is responsible for performing the action.
- PhoenixQA is responsible for recovering the ABILITY to perform that
  action after a failure.
- The test is responsible for judging whether the application's
  behavior was correct.

This keeps PhoenixQA a self-healing framework, not a framework that
gradually absorbs test-framework responsibilities. If deeper validation
hooks turn out to be genuinely needed once Sprint 6-8 produce real usage
patterns, the right move is a generic, opt-in policy/hook mechanism
(`AutonomousPolicy(validator=...)` or `HealingHooks(after_retry=...)`)
layered onto the whole Autonomous Mode configuration — NOT a parameter
bolted onto every single `click()`/`fill()` call. Easier to add an
extensible mechanism later than to walk back a callback-per-action API
that's already spread through a codebase.

### Sprint 5 scope, finalized

✔ heal (existing pipeline from Sprint 2-4)
✔ retry (existing, from BasePage)
✔ stop conditions (`HealingBudget`, `max_attempts_total`/tokens/time)
✔ confidence gate (`AutonomousPolicy.min_confidence`)
✔ three distinct exception types
✘ business/correctness validation — deliberately NOT in scope; remains
  the test's responsibility, as it already is today

### Implementation: Sprint 5 code written, 41/41 unit tests pass

Built exactly to the design above, with one necessary refactor discovered
along the way: `BaseProvider.analyze_failure()` had to change its return
type from a bare `HealingProposal` to a new `ProviderResult` wrapper
(`proposal` + `input_tokens`/`output_tokens`/`elapsed_ms`) — `HealingBudget`
needs that token/timing metadata to enforce limits, and the proposal alone
never carried it. This touched `OllamaProvider` (now measures the full
HTTP round-trip via `time.monotonic()` and reads Ollama's own
`prompt_eval_count`/`eval_count` fields), the `AnthropicProvider` stub
signature, and every existing test/mock that constructed a bare
`HealingProposal` from a provider. Chose to update everything now rather
than maintain two competing return-type conventions — better to absorb
this while the codebase is still small.

New files: `phoenix/healing/autonomous_policy.py` (`AutonomousPolicy` for
configured limits, `HealingBudget` for running consumption, separated
per the policy/tracking split discussed above; `HealLifecycleTimer` as a
context manager wrapping the full collect+analyze+apply+retry span).
`Healer` gained `_attempt_heal_safe()` / `_attempt_heal_autonomous()` as
two explicit branches sharing the same collect→analyze pipeline, plus the
three new/updated exception types (`HealingLimitExceededError`,
`HealingFailedError`, alongside the existing `HealingRejectedError`).

`AutonomousPolicy` is configurable via `.env` (`AUTONOMOUS_MIN_CONFIDENCE`,
`AUTONOMOUS_MAX_ATTEMPTS_TOTAL`, etc.) so the policy isn't only
constructible from Python — `Healer.__init__` builds a default policy
from `Settings` when none is passed explicitly.

Unit tests (`tests/unit/test_autonomous_policy.py`,
`tests/unit/test_healer.py`) cover: budget consumption and the
total-vs-per-selector distinction, token limits tripping independently
of attempt count, the budget-exceeded check blocking a provider call
before it happens (confirmed via `assert_not_called()`), a provider
exception still consuming budget, and confidence-threshold rejection
with no human prompt involved. All mocked — no live page or LLM call
needed for any of these; that verification is the next step, against
real Chaos App + Ollama, same as Sprint 4's eventual live run uncovered
real bugs unit tests alone couldn't.

### Verified live: Autonomous Mode runs end-to-end with zero terminal prompts

First real run with `HEALING_MODE=autonomous` against Chaos App + Ollama
(llama3.2). Initial confusion: the run still showed Safe Mode's terminal
prompts and `"mode": "safe"` in the decision log — turned out `.env`
still had `HEALING_MODE=safe`, an easy miss since `.env.example` had
been updated earlier but `.env` itself is gitignored and never
auto-updated by any file swap. Same category of gotcha as the earlier
`OLLAMA_MODEL` default mismatch — worth remembering as a pattern: when
something "should have changed" but didn't, check `.env` itself before
suspecting the code.

With `.env` corrected, the real run confirmed the full design:
- **Zero terminal prompts** for the entire run — confirms
  `_attempt_heal_autonomous()` actually executes, not just the mocked
  unit-test path.
- **High-confidence proposals (0.85-0.95) auto-accepted**: `username`,
  `password`, and `btn-login` all healed and retried successfully with
  no human involved, in a separate run.
- **Zero-confidence proposal auto-rejected, no hang**: a `password` heal
  hit the same known truncated-JSON failure mode as Sprint 4 (verbose
  `reasoning` field, model cut off mid-generation). Parser correctly
  returned `confidence=0.0`; `Healer` correctly rejected it against the
  `0.75` policy threshold with a clear message — `"Autonomous policy
  rejected proposed fix '' ... confidence 0.00 below policy threshold
  0.75"` — and the run continued, never blocking on `input()`.
- **`is_visible(MSG_WELCOME)` assertion still fails** — same known,
  already-documented scope boundary (`is_visible()`/`get_text()` have no
  `healing` parameter), not a new bug. Confirms this boundary holds the
  same way under Autonomous Mode as it did under Safe Mode in Sprint 4.

Sprint 5 is now verified both in isolation (41 unit tests) and live
end-to-end — the core claim ("Autonomous Mode makes its own
accept/reject decision with no human involved, respecting a confidence
policy") is demonstrated working, not just designed.

### Bug found by careful log reading: "mode" field always said "safe", even for Autonomous Mode

Spotted by directly inspecting `healing_decisions.log` after the live
Autonomous Mode run above — every entry said `"mode": "safe"`, including
ones confirmed (via the absence of any terminal prompt) to have gone
through `_attempt_heal_autonomous()`. Root cause: `log_decision()` had
hardcoded `"mode": "safe"` since Sprint 4, with a comment saying "Sprint
5 will log autonomous from the other path" — but when Sprint 5's
`_attempt_heal_autonomous()` was written, its `log_decision()` call never
actually passed a mode override, so the hardcoded value silently won
every time, from both code paths.

This is the same category of bug as the rotation-suffix regex (Sprint 2)
and the truncated-JSON classifier gap (Sprint 4) — looks completely fine
by inspection (the log writes, the JSON is well-formed, every other field
is correct), and only surfaces by actually reading the output critically
rather than just confirming "no exception was raised." Worth naming as a
recurring pattern: a field that's silently wrong is more dangerous than
a missing field, because nothing fails loudly to reveal it.

Consequence if left unfixed: any future Safe-vs-Autonomous comparison
(Sprint 6/7 Healing History, Sprint 8 benchmark) built on this field
would have been silently corrupted — every Autonomous Mode decision
miscounted as Safe Mode.

Fix: `log_decision()` now takes an explicit `mode` parameter (defaulting
to `"safe"` for backward compatibility with existing call sites that
genuinely are Safe Mode), and `Healer` passes `mode="safe"` /
`mode="autonomous"` explicitly from each of its two branches. Two new
unit tests protect this: one confirming `mode="autonomous"` is correctly
recorded, one confirming the default still produces `"safe"` when not
specified. 43/43 unit tests pass.

### Verified: mode fix confirmed live, all 5 entries correctly labeled

Re-ran the same Autonomous Mode scenario after the fix. All 5 log
entries now correctly show `"mode": "autonomous"`, including the
zero-confidence auto-rejection case — confirming the fix works in the
real code path, not just in mocked unit tests.

### Future consideration: richer decision log fields (most already exist in memory, just not wired to the log yet)

Raised in follow-up discussion: `healing_decisions.log` could carry more
diagnostic fields per entry — `provider`, `decision` (richer than a bare
`accepted: bool`), `elapsed_ms`, `input_tokens`, `output_tokens`,
`attempt`. Worth splitting into two buckets, since they have very
different cost/risk:

**Small, safe to add anytime — pure wiring, no new logic:**
- `provider` — `self.settings.ai_provider` is already available in
  `Healer`, just never passed to `log_decision()`.
- `elapsed_ms` / `input_tokens` / `output_tokens` — already captured in
  `ProviderResult` (Sprint 5) and consumed by `HealingBudget`; currently
  thrown away after budget tracking instead of also being logged.
- `attempt` — `HealingBudget.attempts_for(selector)` already computes
  this; just needs to be read and included.

These four are genuinely just "stop discarding data we already have,"
not new design work — safe to add in a small pass whenever convenient,
no architectural decision required.

**Larger, deliberately deferred — needs real design work first:**
- `decision` as a richer enum (e.g. `AUTO_APPLIED` / `AUTO_REJECTED` /
  `HUMAN_APPROVED` / `HUMAN_REJECTED`) instead of a bare `accepted: bool`.
  Today, `accepted: false` doesn't distinguish "zero confidence, nothing
  to evaluate" from "human said no" from "autonomous policy threshold
  not met" — those are three different stories currently flattened into
  one boolean. Worth designing this vocabulary once, deliberately,
  alongside Sprint 6/7's `history_store.py` schema (which already needs
  to resolve Gap #1, healing correctness) — rather than picking enum
  values now and re-doing it when the real schema gets designed.

### Future consideration: Allure Healing Dashboard instead of accumulated screenshots

Raised in follow-up discussion, directly replacing the "Demo" section's
original plan (a handful of terminal screenshots). One dashboard with
several widgets tells a much stronger story than a pile of individual
screenshots — same underlying argument as Gap #9's heuristic control:
a single well-designed comparison communicates more than scattered
point-in-time evidence.

Proposed widgets: success rate, healing timeline, confidence
distribution, top repaired selectors, failure reasons, budget usage,
provider comparison (No Healer / Heuristic / LLM — directly visualizing
the Gap #9 benchmark result).

Important dependency noted: "budget usage" and "provider comparison"
widgets directly require the richer log fields above (`elapsed_ms`,
tokens, `provider`) — these two future-ideas aren't independent, the
dashboard is the consumer of the enriched log. Sequencing: enrich the
log first (small fields now or in Sprint 6), build `history_store.py`
(Sprint 6/7) and the benchmark runner (Sprint 8), THEN the Allure
dashboard (Sprint 9) has real data to render instead of placeholder
numbers.

### Implemented now (not deferred): the "small bucket" log fields

Per direct discussion, decided to do the small/safe bucket immediately
rather than wait for Sprint 6 — `provider`, `elapsed_ms`, `input_tokens`,
`output_tokens`, `attempt` added to `log_decision()` as optional
parameters (defaulting to `None` so older call sites without this data
still log valid entries). `decision` enum confirmed deferred per direct
agreement ("decision może poczekać").

One real bug caught while wiring this through: existing `test_healer.py`
mocks used `MagicMock()` for `settings` without setting `ai_provider` to
a real value — once `Healer` started reading `self.settings.ai_provider`
to log it, `json.dumps()` choked on trying to serialize a `MagicMock`
object. Same lesson as Sprint 2/4's other "looks fine until you actually
exercise the new code path" bugs — fixed by setting `settings.ai_provider
= "ollama"` explicitly in the test helper. Also added a dedicated test
(`test_log_entry_includes_provider_tokens_and_attempt_number`) that reads
back the actual log file content rather than just confirming "no
exception was raised" — verifying a logging fix by checking the log
itself, not by absence of a crash. 44/44 unit tests pass.

Note: in Autonomous Mode, `elapsed_ms` logs the FULL collect+analyze
lifecycle via `HealLifecycleTimer` (matching what `max_time_per_heal_ms`
actually measures), not just the LLM call's own `ProviderResult.elapsed_ms`
— the two numbers differ and the log intentionally keeps the one that
matches the budget check it sits next to.

## Process reflection (not a sprint change)

A morning-after observation worth recording verbatim in spirit, because
it's a genuinely useful meta-comment on how this project has actually
been built, not a technical decision:

PhoenixQA's SDLC has been inverted relative to a classical V-model. The
project started from a single, narrow requirement ("the self-healer will
heal locators") and every subsequent requirement — failure type
classification, confidence policy, stop conditions, the heuristic
control, business-validation boundaries — was DISCOVERED through
building, not specified up front. Genuinely Agile/incremental in
practice, but also genuinely backwards from "requirements → design →
build → test" as a textbook would draw it. 13+ years of QA instinct
correctly flags this as unusual — and also correctly recognizes it as
how real incremental product development actually happens, as opposed
to the V-model fiction.

**Concrete consequence for Sprint 8 (Healing Benchmark Runner):** because
the whole project's STLC has been informal and emergent so far (manual
end-to-end runs catching real bugs, ad-hoc but rigorous), Sprint 8 is the
moment to do a PROPER STLC pass — not just write a benchmark runner as
more code, but treat the benchmark itself as something requiring genuine
test planning: a clear test strategy (what is actually being measured
and why), defined entry/exit criteria (when is a benchmark run
considered complete and trustworthy), and — critically — validation of
the benchmark's own measurement validity before trusting its output.

Why this matters specifically for Sprint 8: the entire Gap #9 narrative
("we measured whether the LLM was actually necessary, rather than
assuming it") only holds up if the measurement itself was done properly.
An informally-built benchmark producing a number nobody rigorously
validated would undercut the exact R&D credibility the heuristic control
was designed to provide. Not a scope change — a reminder to apply real
STLC discipline specifically at the one sprint where the project's
output is itself a measurement instrument, not a feature.

---

## Sprint 6 (pre-coding) — Failure type expansion: four architectural decisions before writing code

### Why this round of gap analysis matters more than the previous ones

Every prior sprint's gap analysis (Gap #4 in Sprint 2, Gap #10/#11 in
Sprint 5) was found by trying to write pseudo-code and noticing it didn't
fit. This time the gaps were found BEFORE any pseudo-code — a direct,
critical review of the Sprint 6 plan surfaced four decisions that each
reshape a core abstraction (`ContextCollector`, `HealingProposal`, the
prompt layer) before a single `DetachedFromDomCollector` line gets
written. Confirmed instinct from Sprint 2: "better to prove the full
pipeline on one well-understood failure type first" — but the corollary,
now that a SECOND failure type is actually being built, is that the
abstractions designed around ONE failure type (`SELECTOR_NOT_FOUND`) need
to be checked for whether they generalize, not assumed to.

Agreement reached in direct discussion: not only should this gap analysis
happen before code, it should go FURTHER than previous sprints' analyses —
Sprint 5 already showed that "the bigger the scope taken at once, the
higher the chance of an architectural gap surfacing mid-sprint." Sprint 6
responds by both resolving four decisions up front AND splitting
implementation into sub-sprints (see below) rather than one continuous
Sprint 6 push.

### Decision #1 (→ Gap #12, NEW) — "recover selector" vs "recover action"

For `SELECTOR_NOT_FOUND` the framing was always clean: selector stops
resolving → LLM proposes a new selector → done. `DETACHED_FROM_DOM` breaks
this framing at the root, not at the edges:

```
selector resolves fine
        │
element exists
        │
framework re-renders mid-action
        │
old element node is gone, a new (structurally identical) one exists
```

There is no "broken selector" to replace here — the selector may well
still be correct. What actually failed is the ACTION (the click/fill
against a specific element reference), not the LOCATOR STRING. Playwright
already retries a locator against the live DOM by default; what it does
NOT do is retry an in-flight action after the target it had committed to
disappeared mid-click. This means `Healer` for `DETACHED_FROM_DOM` isn't
proposing a replacement selector — it's proposing a RECOVERY STRATEGY for
an interrupted action (re-locate + retry, wait-and-retry, etc.).

**Decision:** `DETACHED_FROM_DOM` (and, by the same reasoning, `NOT_VISIBLE`
and `TIMEOUT_WAITING`) are not "selector healing" — they're "action
recovery." `SELECTOR_NOT_FOUND` is the special case where recovery happens
to mean "propose a new selector." This is now the intended reading of
Gap #4's original framing ("selector healer" vs "UI automation healer"
are the same higher-level problem) — Sprint 6 is where that framing has
to actually be load-bearing in the code, not just in prose. Filed as
**Gap #12** in `docs/gaps.md` since it's a genuinely new architectural
question, not a restatement of Gap #4 (Gap #4 was "should we build this
at all"; Gap #12 is "what does the abstraction look like now that we are").

### Decision #2 — ContextCollector becomes polymorphic, not an if/elif ladder

Current `ContextCollector.collect()` (Sprint 2) routes on `failure_type`
with a single `if failure_type == SELECTOR_NOT_FOUND: ... else: raise
NotImplementedError`. Extending this with three more branches, each
needing DIFFERENT collected data (DOM subtree for selector matching vs.
timing/mutation-observer data for detachment vs. computed-style/overlay
data for visibility), is exactly the kind of branching that starts to
smell once a third and fourth branch join a second — enough real
divergence in what each branch actually DOES that a shared function body
stops being a convenience and starts being a liability.

**Decision:** introduce a `BaseContextCollector` (ABC) with one
`collect(broken_selector, error, original_code) -> HealingContext`
method, and one concrete subclass per `FailureType`:

```
phoenix/collector/
├── context_collector.py       # becomes a thin router/factory, mirrors
│                               # provider_factory.py's existing pattern
└── collectors/
    ├── selector_collector.py      # today's _collect_selector_context, moved as-is
    ├── detached_collector.py      # NEW, Sprint 6B
    ├── visibility_collector.py    # NEW, future sprint
    └── timeout_collector.py       # NEW, future sprint
```

`ContextCollector.collect()` keeps its role as the single entry point
`Healer` calls, classifies via `classify_playwright_error()` same as
today, then delegates to the matching subclass instance. No behavior
change for `SELECTOR_NOT_FOUND` — this is a pure refactor for that path,
with the payoff showing up in Sprint 6B onward.

### Decision #3 — the prompt layer splits the same way

`prompt_templates.py`'s `SYSTEM_PROMPT` is written entirely around "find
a replacement selector in this HTML." For `DETACHED_FROM_DOM` the task
given to the model is categorically different — not "find X in this
snapshot" but "given this sequence of DOM mutation events / timing data,
should the action be retried, and after what wait?" These are different
COGNITIVE tasks for the model, not just different template strings —
conflating them into one big prompt with conditional sections would
produce a worse prompt for both cases than two focused ones.

**Decision:** mirror Decision #2's structure in the prompt layer:

```
phoenix/ai/prompts/
├── selector_prompt.py     # today's SYSTEM_PROMPT + build_user_prompt, moved as-is
├── detached_prompt.py     # NEW, Sprint 6C
├── visibility_prompt.py   # NEW, future sprint
└── timeout_prompt.py      # NEW, future sprint
```

`prompt_templates.py` keeps a small `get_prompt_for(failure_type)` router
function so `OllamaProvider`/`AnthropicProvider` don't need to know which
prompt module to import directly.

### Decision #4 — `HealingProposal` cannot stay the universal return type

This is the decision with the widest blast radius, so it's flagged loudly
rather than folded in quietly. `HealingProposal` today is:

```python
proposed_selector: str
confidence: float
reasoning: str
alternative_selectors: list
```

This shape is meaningless for `DETACHED_FROM_DOM` — there is no
"proposed_selector" to give if the actual proposal is "wait 400ms and
retry the click." Forcing every future failure type's output through
`proposed_selector` would mean either (a) abusing that field to carry
non-selector data as a string, which corrupts its meaning for every piece
of downstream code that reads it (decision logger, Safe Mode terminal
display, Autonomous Mode's confidence gate), or (b) bolting on
`wait_ms: Optional[int] = None`, `retry: Optional[bool] = None`, etc. as
more and more optional fields on one dataclass — the same anti-pattern
already rejected once, for a different reason, in Gap #11's "Option A"
(a callback-per-action API accumulating parameters over time).

**Decision:** introduce a small `HealingAction` type hierarchy, with
`HealingProposal` becoming (in effect) the `SELECTOR_NOT_FOUND`-specific
member of that hierarchy rather than the universal type:

```python
class HealingAction(ABC):
    confidence: float
    reasoning: str

@dataclass
class SelectorReplacement(HealingAction):
    proposed_selector: str
    alternative_selectors: list = field(default_factory=list)

@dataclass
class RetryStrategy(HealingAction):        # DETACHED_FROM_DOM
    wait_ms: int
    reacquire_locator: bool

@dataclass
class WaitStrategy(HealingAction):         # TIMEOUT_WAITING
    wait_ms: int

@dataclass
class VisibilityStrategy(HealingAction):   # NOT_VISIBLE
    action: str   # e.g. "scroll_into_view", "dismiss_overlay", "wait"
```

**Sprint 6 scope:** declare the hierarchy now (same move as the
`FailureType` enum in Sprint 2 — declare the shape so nothing needs
reshaping later, implement only what's needed this sprint). Only
`SelectorReplacement` and `RetryStrategy` get real provider
implementations in Sprint 6; `WaitStrategy`/`VisibilityStrategy` stay
declared-not-implemented until their own sprints, exactly like
`FailureType`'s unimplemented branches did in Sprint 2.

**Required refactor, not optional:** `ProviderResult.proposal` becomes
`ProviderResult.action: HealingAction`, and every call site that reads
`proposal.proposed_selector` / `proposal.confidence` directly (`Healer`,
`safe_mode.py`'s terminal display, `decision_logger.py`) needs updating
to branch on the concrete `HealingAction` subtype, or to rely on fields
common to the base class (`confidence`, `reasoning`) where it can stay
type-agnostic. `response_parser.py`'s fallback (`_fallback_proposal`)
also needs an equivalent per-action-type fallback path. Tracked as a
blocking Sprint 6 sub-task, not a "nice to have" — same seriousness as
Sprint 5's `HealingProposal → ProviderResult` refactor, which touched the
same breadth of call sites.

### Decision: Sprint 6 is broken into sub-sprints, DETACHED_FROM_DOM only

Same instinct as Sprint 2's "prove one failure type end-to-end before
generalizing," applied one level deeper this time — even within ONE new
failure type, the pipeline gets built and verified in thin vertical
slices rather than all four layers (classifier → collector → prompt →
strategy) at once:

| Sub-sprint | Scope | Exit criterion |
|---|---|---|
| 6A | `chaos_app/src/chaos/componentRemount.jsx` (per existing spec) + classifier extended to recognize `DETACHED_FROM_DOM` | Classifier correctly returns `DETACHED_FROM_DOM` on a real remount-mid-action failure — verified live. **Zero healing logic touched.** |
| 6B | `DetachedFromDomCollector` (Decision #2) | Collector gathers real timing/mutation context from a live page — verified against real Chaos App, not yet fed to an LLM |
| 6C | `detached_prompt.py` (Decision #3) | Prompt produces a parseable `RetryStrategy`-shaped response against real Ollama output |
| 6D | `Healer._attempt_heal_*` branches handle `RetryStrategy` end-to-end | Full collect→analyze→apply→retry loop confirmed live for `DETACHED_FROM_DOM`, both Safe and Autonomous Mode |

`NOT_VISIBLE` and `TIMEOUT_WAITING` are explicitly NOT started until
6A-6D are done and verified — same sequencing logic as Sprint 2→3→4→5,
and the same reason: each vertical slice has historically surfaced a real
bug (Sprint 4's `fill()` vs `click()` classifier gap, Sprint 5's
mode-logging bug) that would have been masked by building breadth-first.

### Reaffirmed philosophy: divergence over unification

Explicit, deliberate stance for Sprint 6 and beyond, confirmed in direct
discussion: PhoenixQA does NOT try to collapse `selector_not_found` /
`detached_from_dom` / `not_visible` / `timeout_waiting` into one generic
"AI fixes it" mechanism. The README already stated this ("more than one
root cause") as a framing choice; Sprint 6 is where it becomes an
architectural commitment — `BaseContextCollector` subclasses, per-type
prompts, and a `HealingAction` hierarchy are MORE code than a single
unified path would be, and that's treated as a sign of a correctly-shaped
architecture for this problem, not as premature complexity. The
alternative — one `ContextCollector`, one prompt, one `HealingProposal`
shape stretched to cover four unrelated failure modes — would look
simpler on a diagram and be actively wrong the moment failure type #3
needed data #1 and #2 never needed. If, after Sprint 6, the codebase has
more specialized components than shared logic, that is read as a sign of
a well-fitted architecture, not over-engineering.

---

## Sprint 6A — component remount mechanism + classifier extension (implemented, pending live verification)

**Retrofit note:** this sprint's entries were written chronologically as
the work happened, mixing decision/implementation/verification/
conclusion/follow-up in the order conversations actually occurred — the
sprint ran long enough (four escalating experiments, two unrelated bugs
found along the way) that this is now the first entry worth applying a
stricter structural convention to, going forward. Subsection headers
below are tagged with `[Decision]` / `[Implementation]` / `[Verification]`
/ `[Conclusion]` / `[Follow-up]` as a light retrofit — signposting only,
no prose rewritten — so the phase of each entry is scannable without
reading it top to bottom. This tagging convention applies to **new**
sprint entries from here on; the rest of this file's history is
deliberately left as originally written (see this file's intro: the
chronological journal shows the actual thinking process, not a cleaned-up
version of it).

### [Decision] Design refinement from direct discussion: remount CAUSE, not just remount EXISTENCE

Before writing `componentRemount.jsx`, the initial one-size-fits-all "chaos
timer" idea was refined into something more useful scientifically. Real
component remounts have distinct real-world causes, and a healer's
behavior might plausibly need to differ depending on which one occurred:

- **TIMEOUT** — a periodic re-render unrelated to user interaction (e.g.
  a polling subscription re-rendering its container).
- **STATE_CHANGE** — typing → validation → re-render. Very common in
  form-heavy enterprise UIs.
- **NETWORK_RESPONSE** — click → `fetch()` → response → component
  recreated. Judged the second-most-common real enterprise case after
  TIMEOUT, based on direct experience.

This turns Chaos App from testing "does DETACHED_FROM_DOM handling exist
at all" into eventually testing "does the Healer's behavior correctly
depend on WHY the detachment happened" — a more interesting scientific
question, one level beyond what Sprint 6A itself answers.

**Decision: implement ONLY `RemountTrigger.TIMEOUT` in Sprint 6A.** Same
phased-rollout instinct as `FailureType` in Sprint 2 and `CHAOS_LEVELS`
in Sprint 1 — declare the full enum now (`TIMEOUT`, `STATE_CHANGE`,
`NETWORK_RESPONSE`) so `componentRemount.jsx` doesn't need reshaping when
the other two get built, but implement one variant fully rather than
three shallowly. `STATE_CHANGE` is tentatively slotted for Sprint 8/9,
`NETWORK_RESPONSE` for Sprint 10 — not committed dates, just a plausible
sequencing noted for future reference. Requesting an unimplemented
trigger throws immediately and loudly (mirrors the Python-side
`NotImplementedError` convention already used in `context_collector.py`
and `failure_classifier.py`) rather than silently no-op'ing.

### [Decision] Design refinement: remount ONE component, not the whole form

A second refinement from the same discussion: remounting an entire
`<form>` would be a much cruder simulation than what real frameworks
actually do. React reconciliation and Lightning re-renders typically
replace one component at a time, leaving siblings untouched — a
`<button>` gets recreated while the inputs around it are undisturbed, not
"the whole screen goes away and comes back."

**Decision:** `ComponentRemountWrapper` wraps exactly one child element.
Implementation forces a genuine DOM node replacement (not just a
re-render) by changing the wrapped child's `key` prop on a timer — React
treats a key change as "this is a different element" and tears down the
old DOM node rather than patching it in place. This distinction matters:
a same-node re-render would never actually produce a
`DETACHED_FROM_DOM`-shaped Playwright failure, since Playwright would
just see the same node with possibly-updated attributes.

**Decision: repeats on an interval (200-800ms), not a single one-shot
remount.** A single remount only rarely collides with an in-flight
Playwright action. A repeating remount both matches real re-render loops
(which recur, not fire once) and meaningfully increases the odds that a
live test run actually reproduces the target failure within a normal
test timeout window.

### [Decision] Target the login submit button, continuing the same research story

Consistent with the project's established pattern of changing one
variable at a time (Sprint 2's "prove SELECTOR_NOT_FOUND fully before
generalizing," Sprint 6's "prove DETACHED_FROM_DOM fully before
NOT_VISIBLE/TIMEOUT_WAITING"): the first `DETACHED_FROM_DOM` target is
`LoginForm`'s submit button, not a new component or a different form.
Sprint 2 through 5 were all built and verified against the same login
flow — introducing a new failure type AND a new UI scenario
simultaneously would confound which variable caused what, if something
doesn't work as expected on the first live run. Login is also the
simplest possible case to reason about (`fill → fill → click → element
detached`) and the natural first row in the eventual Sprint 8 benchmark
table, for the same reason `selector_not_found` used login first.

**Consequence:** `component_remount` joins `shadow_dom` as an
INDEPENDENT flag (`COMPONENT_REMOUNT_ENABLED` / `VITE_COMPONENT_REMOUNT_
ENABLED`), not a member of `CHAOS_LEVELS`. Same reasoning as Sprint 1's
Shadow DOM decoupling: this isn't "more chaos" on the
selector-rename/DOM-mutation/timing axis the levels already cover — it's
a different failure family entirely, combinable with any level (e.g.
`HIGH + component_remount_enabled` is a valid, meaningful combination
once Sprint 7's benchmark runner exists to actually run it).

### [Implementation] Classifier extended, ContextCollector untouched (as scoped)

`classify_playwright_error()` gained a new check for
`DETACHED_FROM_DOM`, based on substring matches against Playwright's
documented actionability-check vocabulary (`"not attached to the dom"`,
`"element is not attached"`, `"was detached from the dom"`). Checked
**before** the existing `"waiting for locator"` check, because a
detached-mid-action message also contains that phrase (Playwright logs
it for every action) — the more specific "not attached" signal has to
win, or every `DETACHED_FROM_DOM` failure would silently misclassify as
`SELECTOR_NOT_FOUND`.

`ContextCollector.collect()` is UNCHANGED apart from a clarified
`NotImplementedError` message pointing at Sprint 6B specifically — per
the Sprint 6A exit criterion, zero collection or healing logic was
touched this sub-sprint. A `DETACHED_FROM_DOM` failure today still
raises `NotImplementedError` after being correctly classified; that's
the intended state until Sprint 6B ships `DetachedFromDomCollector`.

**Honest epistemic flag, consistent with how this file has always
handled classifier changes:** the substrings above are inferred from
Playwright's public actionability-check documentation, not yet captured
from a real Playwright error produced by `componentRemount.jsx` running
against a live browser. Sprint 2's original classifier and Sprint 4's
`fill()`/`click()` fix both needed correction after a real end-to-end run
revealed a message shape hand-crafted samples didn't anticipate — there
is no reason to expect this branch is exempt from that same pattern.
Four new unit tests (`TestClassifyPlaywrightErrorDetachedFromDom`) cover
the hand-crafted samples, including the critical ordering case (detached
message that also contains "waiting for locator" must still classify as
`DETACHED_FROM_DOM`), but these are NOT a substitute for a live run —
same distinction this project has drawn since Sprint 2's "unit tests
pass" vs. "pipeline works end-to-end."

**Sprint 6A exit criterion status: implemented, live verification
pending.** The classifier-only exit criterion from the Sprint 6 sub-sprint
table ("classifier correctly returns DETACHED_FROM_DOM on a real
remount-mid-action failure — verified live") requires an actual
`pytest tests/chaos/ -m chaos -s` run against Chaos App with
`COMPONENT_REMOUNT_ENABLED=true` / `VITE_COMPONENT_REMOUNT_ENABLED=true`
on both sides. Not yet run as of this entry. Next concrete step before
Sprint 6A is considered closed — same discipline as every prior sprint's
"built and unit tested" vs. "verified live" distinction.

### [Verification] Bug found during first live test run after Sprint 6A changes: BasePage never actually caught Healer's decline exceptions

First `python -m pytest tests/chaos/ -m chaos -s` run after copying the
Sprint 6A files in produced a confusing failure — NOT related to
`componentRemount.jsx` at all (that mechanism wasn't even enabled yet;
`COMPONENT_REMOUNT_ENABLED` defaults to `false` and the run used
defaults). `failure_type: "selector_not_found"` in `healing_decisions.log`
confirmed this: `username` and `password` healed and were accepted
normally (autonomous mode), but `btn-login` hit the same already-known
Ollama truncated-JSON failure mode documented repeatedly since Sprint 4
(verbose `reasoning` field, model cut off mid-generation) — nothing new
about the LLM behavior itself.

What WAS new: the test failed with

```
phoenix.healing.healer.HealingRejectedError: Autonomous policy rejected
proposed fix '' for broken selector '[data-testid='btn-login']':
confidence 0.00 below policy threshold 0.75
```

— not the underlying `playwright._impl._errors.TimeoutError` that
actually triggered healing in the first place. This directly contradicts
what `healer.py`'s own docstrings have said since Sprint 4/5:
`HealingRejectedError`'s docstring states "the ORIGINAL test failure is
what should actually be reported... let the original Playwright error
surface to pytest rather than this one," and the `Healer` class docstring
says the same for all three exception types. Checked `pages/base_page.py`
directly: `click()`/`fill()` catch `PlaywrightTimeout` and call
`attempt_heal()`, but never wrapped that call in a `try/except` for
`HealingRejectedError` / `HealingLimitExceededError` / `HealingFailedError`
— so whichever of those three the Healer raised propagated straight to
pytest instead of the original timeout. Documented design intent and
actual implementation had quietly diverged since Sprint 4, and nothing
had exercised this exact path clearly enough to surface it — in Safe
Mode a human typically accepts good proposals, and prior Autonomous Mode
live runs (Sprint 5) apparently didn't examine the pytest-level failure
message closely enough to notice the mismatch, only the decision log.

This is the same category of bug as the Sprint 2 rotation-suffix regex
and the Sprint 5 hardcoded log mode: looks completely fine by
inspection (the code runs, an exception IS raised, the test DOES fail as
a failing heal should), and only surfaces by checking that the RIGHT
exception is what's actually surfacing — "a test fails" and "a test
fails with an actionable, correct message" are different claims, exactly
Gap #1's underlying "test passing ≠ correctness" concern showing up in
error reporting rather than in healing correctness this time.

**Fix:** `BasePage.click()`/`fill()` now wrap `attempt_heal()` in a
`try/except` for the three decline exceptions and re-raise the ORIGINAL
Playwright exception (`e`) — matching the documented contract exactly.
The full "why healing failed" detail (confidence, raw LLM response,
reasoning) remains available in `healing_decisions.log` for anyone who
needs to diagnose it; pytest's own failure report goes back to being the
same clean, familiar `TimeoutError` a reader would expect whether or not
healing was even enabled. Six new unit tests
(`tests/unit/test_base_page.py`) cover all three decline exception types
for both `click()` and `fill()`, plus regression coverage for the
successful-heal and healing-disabled paths, using a mocked `Healer` (no
live page or LLM needed — same testing posture as `test_healer.py`).
25/25 unit tests pass.

**Note for the still-pending Sprint 6A live verification:** this fix is
orthogonal to whether the `DETACHED_FROM_DOM` classifier substrings are
correct — that question is still open and needs a run with
`COMPONENT_REMOUNT_ENABLED=true` (root `.env`) AND
`VITE_COMPONENT_REMOUNT_ENABLED=true` (`chaos_app/.env`, chaos app dev
server restarted after the change) on both sides. Today's run, by
coincidence, surfaced a real but unrelated bug before Sprint 6A's actual
mechanism was ever exercised — worth remembering as a reminder that a
red test run can be carrying more than one finding at once, and each one
deserves its own diagnosis rather than being attributed to whatever
change was most recent.

### [Verification] Recurring pattern confirmed: `chaos_app/.env` didn't pick up the new flag either

Same live-verification session, same underlying cause as the root `.env`
gotcha above, just on the Chaos App side this time: `VITE_COMPONENT_
REMOUNT_ENABLED` was added to `chaos_app/.env.example` but never
propagated to the real, gitignored `chaos_app/.env` — the debug panel
correctly showed `Component Remount ... disabled` even after a full
`npm run dev` restart, because the env var genuinely wasn't set to
anything, not because Vite failed to pick up a change. Confirms the
Sprint 5 lesson generalizes beyond the Python side: `.env.example`
changes never reach either real `.env` file automatically, on either
side of this repo, and checking the actual gitignored file directly is
always the first move before suspecting the code — this is now the
second time this exact category of gotcha has appeared (Sprint 5:
`OLLAMA_MODEL`/`HEALING_MODE`; Sprint 6A: `VITE_COMPONENT_REMOUNT_ENABLED`).

### [Verification] BasePage correctly re-raises the original Playwright error, confirmed live

The fix documented above was confirmed against a real run: pytest's
`short test summary info` reported `playwright._impl._errors.TimeoutError`
for both failing tests, not `HealingRejectedError` — exactly the intended
behavior. Traceback confirmed the new `except`/`raise e` path was the one
actually taken (`pages\base_page.py:99: in fill / raise e`). This closes
the loop on that fix — implemented, unit tested, and now also confirmed
live, same three-stage verification bar every other fix in this project
has needed.

### [Decision] Mechanism override, replacing a rejected "NONE" level

Attempting to actually reproduce `DETACHED_FROM_DOM` live surfaced a
real, structural problem, not just a timing-luck problem: `ChaosLoginPage`'s
`BTN_SUBMIT` selector is unrotated, but `selector_rotation` is baked into
EVERY `CHAOS_LEVELS` entry (`LOW` already includes it; `MEDIUM`/`HIGH`
only add to it). That means the very first `click()` on the login button
always fails with `SELECTOR_NOT_FOUND` — the element is never live long
enough under a matching selector for `componentRemount.jsx` to ever
detach anything from it. `DETACHED_FROM_DOM` could, at best, only appear
on the RETRY click after a successful heal — a narrow, low-probability
window, not a reliable reproduction path. Same "isolate one variable"
instinct that shaped Shadow DOM's decoupling in Sprint 1: right now
there's no way to run `component_remount` WITHOUT `selector_rotation`
also being active and dominating the failure.

**First proposal: a `NONE` chaos level (zero mechanisms).** Rejected in
direct discussion, for a sharp reason: it conflates two different
things that only looked similar. A chaos level is meant to name an
official, cumulative research scenario (`LOW`/`MEDIUM`/`HIGH`, feeding
the Sprint 7/8 benchmark table) — "zero chaos" is a legitimate scenario
in that sense, but "let me isolate one specific mechanism for
development verification" is a completely different need that just
happens to also want zero mechanisms IN THIS ONE CASE. `NONE` would only
solve isolating `component_remount` specifically. The moment a future
need arises — e.g. "Shadow DOM + Component Remount, without DOM
Mutation" — `NONE` provides nothing; a new named level would have to be
invented for every such combination, which is exactly the kind of
special-casing `CHAOS_LEVELS`'s dict design was built in Sprint 1 to
avoid.

**Resolution: mechanism overrides, not a new level.** Clarified two
classes of mechanism, formalized in `chaosConfig.js`'s module docstring:

- **Core mechanisms** (`selector_rotation`, `dom_mutation`, `async_delay`)
  — the ones `CHAOS_LEVELS` cumulatively ladders through. This class and
  the ladder itself are UNCHANGED by this decision.
- **Independent mechanisms** (`shadow_dom`, `component_remount`, and
  future additions) — already handled by their own flags since Sprint 1
  (Shadow DOM) and Sprint 6A (Component Remount).

The actual gap was that core mechanisms had no equivalent to "force this
one off/on regardless of level." Added `applyMechanismOverrides()` +
optional per-mechanism env vars (`VITE_OVERRIDE_SELECTOR_ROTATION`,
`VITE_OVERRIDE_DOM_MUTATION`, `VITE_OVERRIDE_ASYNC_DELAY`) — each
strictly optional, absent means "use whatever the level already
implies," so every existing Sprint 1-6 run is completely unaffected.
This generalizes to ANY future combination without inventing new named
levels: `LOW + component_remount, rotation forced off` today,
`MEDIUM + shadow_dom, dom_mutation forced off` next month, without
touching `CHAOS_LEVELS` itself either time.

**Explicitly scoped as development/verification-only, never for the
official benchmark.** `CHAOS_LEVELS`'s three named scenarios remain the
only thing Sprint 7/8's benchmark runner should ever configure via plain
`CHAOS_LEVEL` — overrides exist so a human isolating one specific
question during development doesn't need to invent a level for every
such question, not so the benchmark gains a combinatorial explosion of
level×override configurations to report on.

**To verify `DETACHED_FROM_DOM` in isolation**, the recommended
configuration is now:
```bash
# chaos_app/.env
VITE_CHAOS_LEVEL=LOW
VITE_OVERRIDE_SELECTOR_ROTATION=false
VITE_COMPONENT_REMOUNT_ENABLED=true
```
This makes `LoginForm`'s `btn-login` selector stable (no rotation), so
the very first `click()` actually acquires a live element — giving
`componentRemount.jsx`'s repeating remount a real chance to detach it
mid-action, rather than the click failing on `SELECTOR_NOT_FOUND` before
any element was ever held at all.

**Honest caveat, stated up front rather than discovered by surprise
later:** even with this isolation, Playwright's own actionability retry
loop may frequently just re-resolve the (rotated-away-then-back... no,
here: unrotated but remounted) element on its next check and succeed
without ever producing a distinct "not attached" error — because
`click()`'s actual dispatch window is only a few milliseconds wide
against a 200-800ms remount interval. A `DETACHED_FROM_DOM`-shaped
failure may require several runs to actually observe, or may turn out to
need a shorter remount interval to reproduce reliably during
verification specifically (as opposed to the interval chosen for
*realism* in the mechanism's normal/default use). This is itself a
legitimate, useful empirical question for the live verification session
to answer — not a design flaw to pre-emptively "fix" before ever
observing real behavior.

### [Follow-up] Naming/philosophy note (flagged for later, not an immediate change)

Raised in the same discussion, worth recording even though it isn't
actionable yet: `CHAOS_LEVEL` originally meant "how much chaos" (Sprint
1's LOW→HIGH difficulty ladder). Between Shadow DOM (Sprint 1),
Component Remount (Sprint 6A), and now mechanism overrides, it's
increasingly describing "which named research scenario is configured"
rather than a literal difficulty gradient. Not urgent to rename or
restructure anything now — `LOW`/`MEDIUM`/`HIGH` still read naturally
and the Sprint 7/8 benchmark table depends on that naming being stable —
but worth revisiting the framing in documentation (not the code) once
enough independent mechanisms exist that "level" no longer intuitively
describes what's actually being configured. A candidate future framing:
`CHAOS_LEVEL` as a "predefined research scenario," with independent
mechanisms and overrides as orthogonal lenses layered on top — matching
how the project has actually evolved from a self-healing framework demo
into an experimentation platform. Filed as a documentation consideration
for a future sprint, not a Sprint 6 action item.

### [Verification] `LOW + selector_rotation forced off + component_remount` isolation works as designed — but a full run passed with an empty log

First run with the isolation configuration above (`LOW`,
`VITE_OVERRIDE_SELECTOR_ROTATION=false`, `VITE_COMPONENT_REMOUNT_ENABLED=true`)
completed in 12s with both tests PASSING and `healing_decisions.log`
completely empty. Not a bug in `decision_logger.py` (already unit
tested, and pure file I/O with no branching that could silently no-op) —
`log_decision()` is only ever called from inside `Healer.attempt_heal()`,
which is only ever called when `click()`/`fill()` actually raises a
`PlaywrightTimeout` in the first place. With `selector_rotation` off,
`username`/`password`/`btn-login` are stable selectors, so the very
first `click()`/`fill()` succeeded every time — the Healer was never
invoked at all, so there was nothing to log. The dramatically shorter
run time (12s vs. the usual ~190s) is itself confirming evidence: no
timeouts occurred anywhere in the run.

This also confirms the hypothesis flagged as a caveat when the isolation
config was designed: `component_remount`'s default 200-800ms interval
did not happen to collide with either test's click/fill window in this
particular run. Not surprising — a `click()`'s actual dispatch is only a
few milliseconds wide against an interval two orders of magnitude
larger, so a genuine collision within one run is a real possibility, not
a certainty.

**Made the interval configurable rather than re-running blindly or
hand-editing the constant.** `ComponentRemountWrapper` now accepts
optional `minDelayMs`/`maxDelayMs` props (default unchanged: 200-800ms,
the "realistic" range), threaded through from two new optional env vars,
`VITE_COMPONENT_REMOUNT_MIN_MS` / `VITE_COMPONENT_REMOUNT_MAX_MS`. Same
philosophy as every other tunable in this project (`AutonomousPolicy`,
chaos levels, mechanism overrides): a hardcoded constant that someone
would otherwise have to edit and revert by hand for a one-off
verification session becomes a documented, optional, reversible env
var instead. Setting both to something like `50`/`150` for a
verification session makes a collision far more likely within a single
run, without touching the mechanism's realistic defaults for normal use.

### [Decision] + [Implementation] Deterministic MOUSEDOWN trigger, replacing the "tighten the timer" instinct

After confirming the isolation config worked exactly as designed
(`LOW` + `selector_rotation` forced off + `component_remount` on) but a
full test run passed cleanly in 2.52s even with a 50-150ms interval, the
obvious next instinct — "try an even shorter interval, e.g. 10-30ms" —
was raised and deliberately rejected in favor of a different approach,
for a reason worth recording precisely.

**Why not just tighten the interval further:** any timer-based interval,
however short, keeps the question probabilistic — "did the random timer
happen to fire during the click's narrow dispatch window?" A pass at
10-30ms is ambiguous evidence: it could mean Playwright is genuinely
resilient to this failure mode, or it could simply mean this run didn't
get unlucky. A failure at 10-30ms would be equally ambiguous in the
other direction. This is structurally the same problem as papering over
a flaky test by increasing a `sleep()` until it stops failing — it can
work, but it teaches you almost nothing about WHY, and doesn't reliably
replicate. Same "isolate one variable" instinct that has recurred all
sprint (Shadow DOM decoupling in Sprint 1, the rejected `NONE` level,
mechanism overrides): the actual variable worth isolating here isn't
"how short can the interval get," it's "what happens if the element is
replaced at the EXACT moment an interaction begins" — a fundamentally
different, answerable question.

**Decision: add `RemountTrigger.MOUSEDOWN`**, a deterministic trigger
alongside the existing `RemountTrigger.TIMEOUT`. Implementation attaches
a native `mousedown` handler directly to the wrapped element and bumps
the remount `key` synchronously the instant that event fires — no
interval, no randomness. React 18 flushes discrete event updates (like
`mousedown`) before the browser dispatches the next native event in the
same user gesture (`mouseup`, `click`), so by the time Playwright's click
sequence reaches those later events, the OLD DOM node should already be
torn down and a new one mounted in its place. This turns "will a random
timer ever collide with a click?" into "what specifically happens when
detachment occurs at the most adversarial possible moment?" — a
deterministic experiment instead of a probabilistic one.

**A genuinely useful technical hypothesis this also tests:** Playwright's
`click()` dispatches low-level mouse events via CDP at specific page
COORDINATES (like a real user), rather than holding a persistent
reference to a specific DOM node the way e.g. Selenium's `WebElement`
does. If a replacement button renders at the same screen position, the
browser's native hit-testing may simply deliver `mouseup`/`click` to the
NEW node without Playwright ever noticing a swap happened — which would
be a plausible explanation for why the probabilistic `TIMEOUT` runs
haven't produced a visible failure so far. `RemountTrigger.MOUSEDOWN`
gives this hypothesis a fair, deterministic test.

**Explicitly framed as a genuine finding either way, decided before
seeing the result:** if `MOUSEDOWN` reliably produces a
`DETACHED_FROM_DOM`-classifiable Playwright error, Sprint 6B has a real,
reproducible case to build `DetachedFromDomCollector` against. If it does
NOT — even at this maximally adversarial, zero-timing-luck setting —
that is not a failed sub-sprint. It would mean Playwright's
actionability/dispatch pipeline is substantially more resilient to
React `key`-based remounts than the original mechanism design assumed,
and that future Chaos App mechanisms simulating this failure family
should target lower-level DOM mutation or raw browser event timing
rather than a React-level remount. Chaos App exists to simulate real
failure CLASSES, not to force one specific exception message out of
Playwright at any cost — discovering a limit of this particular
simulation approach is exactly the kind of result this project's
empirical, measure-first philosophy is supposed to produce, not a result
to keep pushing against.

### [Conclusion] Sprint 6A conclusion — hypothesis, experiment, finding, interpretation, decision

Recorded deliberately in this structure rather than as a narrative of
"what went wrong," because that's not what this is — it's the project's
first result that reads like a research finding rather than a feature
status update.

**Initial assumption:** `DETACHED_FROM_DOM` was expected to become the
second supported failure family after `SELECTOR_NOT_FOUND`, based on
direct Selenium/Salesforce Lightning experience (Sprint 2's original
`FailureType` design).

**Experiment:** Multiple `componentRemount.jsx` configurations attempted
to reproduce Playwright's `DETACHED_FROM_DOM` failure under controlled
conditions — a random-interval remount (200-800ms), tightened
progressively (100-300ms, then 10-30ms), and finally a deterministic
`mousedown`-triggered remount with zero timing randomness at all:

```
tests/chaos/test_chaos_login.py::TestChaosLogin::test_successful_login PASSED
tests/chaos/test_chaos_login.py::TestChaosLogin::test_invalid_credentials PASSED
2 passed in 2.62s
```

**Finding:** The experiments consistently failed to trigger an
observable `DETACHED_FROM_DOM` failure when PhoenixQA interacted with
the page exclusively through Playwright's `Locator` API — including at
the deterministic, zero-timing-luck setting, which rules out "the
random timer just never happened to collide" as an explanation.

**Interpretation:** Chaos App's mechanism design is not the likely
explanation — four independent, increasingly aggressive attempts,
ending in a deterministic zero-timing-luck trigger, is a lot of surface
area for a mechanism bug to hide in without ever once producing the
target error. A more precise explanation is available directly from
Playwright's own documentation: `Locator` re-resolves elements on every
actionability check, and per Playwright's own `Locator.click()`
reference, the action is simply retried if the target detaches
mid-check. `BasePage` is built entirely on `page.locator(...).click()/
.fill()`, never on `ElementHandle`/`page.$()`, so the exact failure
class Sprint 2's original design was anchored on targets a
reference-holding API this codebase never uses in the first place.

**Scope of this claim, stated precisely rather than generally:** this
result says PhoenixQA's specific interaction pattern (`Locator.click()`/
`.fill()` against a single remounted component, tested up to a
deterministic worst case) did not produce `DETACHED_FROM_DOM` in four
attempts. It does not claim `Locator` is immune to detachment failures
in general, under every Playwright version or interaction shape — see
the real counter-examples below, which is exactly why this is filed as
"deprioritized based on current evidence," not "resolved" or "proven
impossible."

Real "Element is not attached to the DOM" errors DO occur in
`Locator`-based Playwright suites, but the research surfaced three
narrower patterns than what `componentRemount.jsx` was simulating, none
of which are remediated the way PhoenixQA's healing pipeline currently
proposes fixes:
- Code that bypasses `Locator` entirely by storing a `page.$()`/
  `ElementHandle` result and reusing it later (Playwright issue #6244,
  and independently documented by third-party Playwright guides) — a
  `Locator` bypass, not a `Locator` failure; the fix is "stop bypassing
  `Locator`," not a selector swap.
- A narrow, version-specific `check()`/`uncheck()` edge case (Playwright
  issue #10477, v1.16.3, 2021), where the detachment happened in a
  post-action verification step, not the action itself — a framework bug
  fix outside test-author control.
- A genuine, currently-documented race (2026 community writeup, the
  Mergify Playwright flakiness catalog): the exact target element gets
  replaced in the sub-frame gap between the actionability check passing
  and the click event actually firing — remediated in practice by
  anchoring the locator to a stable ancestor so retry naturally resolves
  the replaced child, a locator *structure* change, not a selector
  *swap* (`SelectorReplacement`) and not cleanly a generic wait-and-retry
  either (`RetryStrategy` as currently declared in the Sprint 6
  `HealingAction` hierarchy).

**Decision:** `DETACHED_FROM_DOM` remains a real Playwright failure
type, but the evidence indicates it is not a high-value engineering
target for this project's `Locator`-based healing pipeline right now —
both because four escalating attempts couldn't observe it in PhoenixQA's
own interaction pattern, and because the real occurrences documented
elsewhere aren't remediated in a shape the current `HealingAction`
hierarchy models well. Sprint 6 therefore shifts focus toward failure
types that occur naturally in `Locator` workflows (`NOT_VISIBLE`,
`TIMEOUT_WAITING`) — `asyncDelay.js` already incidentally covers part of
`NOT_VISIBLE`, unformalized since Sprint 2, and Playwright's own
actionability model (visible/enabled/stable/receiving-pointer-events) is
documented to fail in exactly these two ways far more often than via
detachment — while documenting this finding for future reconsideration,
not discarding it. **Deprioritized, not resolved** — the distinction
matters: this is a call about where to spend engineering effort given
current evidence, not a claim that the failure type has been eliminated
or proven not to exist. Which of the two remaining candidates becomes
the actual next target is an open decision, not yet made — see TODO.

**What this does NOT invalidate:** Decisions #1-4 from Sprint 6's
pre-coding gap analysis (action-recovery reframing, polymorphic
`ContextCollector`, split prompt modules, the `HealingAction` hierarchy)
remain sound regardless of which failure type Sprint 6B onward actually
targets — they were designed to generalize across `DETACHED_FROM_DOM`/
`NOT_VISIBLE`/`TIMEOUT_WAITING` collectively, not specifically around
`DETACHED_FROM_DOM`. What changes is only WHICH of the three remaining
failure types gets the next vertical slice.

Sources consulted:
- https://playwright.dev/docs/api/class-locator
- https://playwright.dev/docs/actionability
- https://playwright.dev/docs/input
- https://playwright.dev/dotnet/docs/api/class-elementhandle
- https://github.com/microsoft/playwright/issues/6244
- https://github.com/microsoft/playwright/issues/10477
- https://github.com/microsoft/playwright/issues/19330
- https://mergify.com/blog/playwright-auto-wait-element-rerenders

See `docs/gaps.md` Gap #4 (updated) and `docs/architecture-decisions.md`
for the resulting scope note.

## [Follow-up] Process reflection — Chaos App as a research platform, not just a test target (Sprint 6A)

Worth naming explicitly, the same way Sprint 5's "process reflection"
named the project's inverted SDLC — this is an observation about how
the project is maturing, not a technical decision in itself.

Every mechanism built into Chaos App before Sprint 6A existed to serve
PhoenixQA — give the healer something real to heal. `selector_rotation`,
`dom_mutation`, `async_delay`, `shadow_dom`: each one exists because
PhoenixQA needed a failure to practice recovering from. Sprint 6A's
`DETACHED_FROM_DOM` investigation inverted that relationship for the
first time. `componentRemount.jsx` was built to test a hypothesis about
*Playwright itself* — "does `Locator` behave the way Selenium-era
intuition about stale elements assumes it does, for this project's
specific interaction pattern" — not to hand PhoenixQA a healing target.
The result is a finding about the tool the whole project is built on
top of, not about PhoenixQA's own code.

This matters beyond the one failure type. Early sprints followed a
consistent shape: "PhoenixQA needs a mechanism, so build one." Sprint 6A
followed a different shape: "run a controlled experiment, and let the
result — whatever it is — decide the next architectural move." That's
the difference between extending a framework and operating a research
platform that happens to produce a framework as one of its outputs.
Concretely, this means Chaos App's mechanisms are no longer read as
"inputs PhoenixQA consumes" alone — they're also experimental apparatus
that can produce evidence about Playwright's own behavior, and that
evidence can and did change the roadmap, not just get logged as a note.

The four-step discipline this required — form a hypothesis, build a
controlled experiment escalating toward a deterministic case, treat a
clean null result as real information rather than a problem to route
around, and change the plan based on what was actually observed rather
than what the roadmap already said — is a more mature posture than
defending a pre-written sprint plan against inconvenient data would have
been. Worth carrying forward explicitly into however `NOT_VISIBLE`/
`TIMEOUT_WAITING` gets investigated next: build the experiment first,
let the result choose the strategy, not the other way around.

---

## Sprint 6B (pre-coding) — classifier diagnostics before choosing a collection target

### [Decision] Investigate before choosing between `NOT_VISIBLE` and `TIMEOUT_WAITING`

Following through on the previous section's own closing line. Before
picking a Sprint 6B target, a structural concern was raised: `TIMEOUT_WAITING`
is defined as "never reached an actionable state," which is close to a
superset of what `NOT_VISIBLE` means ("in DOM, but hidden"). If
Playwright's own error messages can't reliably distinguish these two at
the point `classify_playwright_error()` runs, choosing between them as
separate top-level `FailureType` values would repeat Gap #5's original
problem — a classifier that can't actually tell its own categories
apart — one layer deeper than the `fill()`/`click()` message-shape gap
found in Sprint 4.

**Decision:** run small, targeted diagnostic experiments against real
Playwright output before deciding anything architectural. Same standing
rule adopted after Sprint 6A (see `docs/architecture-decisions.md`,
"Documentation structure"): don't generalize from documentation or
plausible-sounding reasoning when the real message shape can just be
captured directly. Each diagnostic below is a throwaway test file
(`tests/chaos/test_diagnostic_*.py`), deleted immediately after its
result was captured — never part of the permanent suite.

### [Verification] Real production logs: `click()` and `fill()` `SELECTOR_NOT_FOUND` messages are identical, and reason-less

Before running anything new, checked what real (not hand-crafted)
`SELECTOR_NOT_FOUND` messages already sitting in `healing_decisions.log`
actually look like, for both actions:

```
click(), selector never resolves:  "waiting for locator(\"[data-testid='btn-login']\")"
fill(),  selector never resolves:  "waiting for locator(\"[data-testid='username']\")"
```

Both bare, both identical in shape, no trailing "reason" text of any
kind. This is a direct correction of a detail assumed since Sprint 2:
the original hand-crafted `click()` test sample used in
`test_context_collector.py` (`"...to be visible"` appended) turns out to
never have matched real `click()` output for a genuinely non-resolving
selector — it was fictional in the same way the original `fill()`
assumption was, before Sprint 4 caught that one. Neither hand-crafted
sample was malicious or careless; both were reasonable guesses that
happened to be wrong in the same direction, and both were only caught by
checking real output.

### [Verification] `async_delay`'s current implementation collides with `SELECTOR_NOT_FOUND`

Isolated `async_delay` alone (`VITE_CHAOS_LEVEL=HIGH`,
`VITE_OVERRIDE_SELECTOR_ROTATION=false`, `VITE_OVERRIDE_DOM_MUTATION=false`)
and captured a real timeout against `AddItemForm`'s confirmation message
with a deterministic 100ms `wait_for(state="visible")` — well under the
mechanism's 300-2000ms delay window, so this reliably times out every
run rather than depending on luck:

```
'Locator.wait_for: Timeout 100ms exceeded.\nCall log:\n  - waiting for locator("[data-testid=\'item-added-confirmation\']") to be visible\n'
```

This message contains `"waiting for locator"`, so today's classifier
(`if "waiting for locator" in message: return SELECTOR_NOT_FOUND`)
returns `SELECTOR_NOT_FOUND` for it — even though the selector is
completely correct; the element simply isn't in the DOM yet.

Root cause, found by reading `AddItemForm.jsx` directly: the confirmation
is rendered conditionally (`{showConfirmation && <p>...}`), so the
element genuinely does not exist in the DOM at all until it's ready —
architecturally identical, from Playwright's perspective, to a selector
that never matches anything. This is a real, distinct finding from the
message-shape question above: it means `async_delay` as currently built
cannot be used to produce a genuine "element exists but isn't actionable
yet" case — only a "conditionally-not-yet-mounted" case, which Playwright
cannot distinguish from `SELECTOR_NOT_FOUND` no matter how the classifier
is improved, because the information simply isn't in the call log. A
future chaos mechanism aimed at a true actionability case would need to
render the element into the DOM immediately and toggle a CSS/attribute
property (`display:none`, `disabled`, etc.) instead of conditionally
mounting it.

### [Verification] `fill()` reports a granular reason once the locator resolves

Self-contained diagnostic via `page.set_content()` — no running Chaos
App needed — testing `fill()` against a `disabled`, a `display:none`,
and a `readonly` input, each with a 100ms timeout:

```
disabled:  "... - attempting fill action\n    ... element is not enabled\n  - retrying fill action ..."
hidden:    "... - attempting fill action\n    ... element is not visible\n  - retrying fill action ..."
readonly:  "... - attempting fill action\n    ... element is not editable\n  - retrying fill action ..."
```

All three resolve the locator first (`"locator resolved to <input .../>"`,
not shown truncated above) and only then report a specific, distinct
reason. This directly answers the open question from the previous
section: `fill()` DOES support the same granular reporting `click()`
does — the earlier assumption (Sprint 4) that `fill()`'s bare message
meant it never reports a reason was itself incomplete. What Sprint 4
actually observed was the *no-resolution* case (`SELECTOR_NOT_FOUND`);
nobody had yet tested `fill()` against a resolved-but-not-actionable
element to see whether the reason-reporting behavior also applied there.

### [Verification] `click()`'s two remaining actionability reasons — `stable` and `receives events`

Same self-contained approach, testing `click()` against an animating
element (`stable`) and an element covered by a transparent overlay
(`receives events`):

**`receives events` — clean on the first attempt:**
```
"... element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - <div id=\"overlay\">...</div> intercepts pointer events ..."
```
Notably richer than the other four reasons — it names the specific
blocking element (`<div id="overlay">`), not just the condition.

**`stable` — took two attempts to observe correctly, and the failure
mode itself is informative.** First attempt used a CSS `@keyframes`
animation with default easing and a 200ms timeout — the test **passed**
(`click()` succeeded). Root cause: default CSS easing has near-zero
velocity at each keyframe boundary, so two consecutive animation-frame
samples can land close enough together to read as "stable" purely by
chance — the exact same category of problem as Sprint 6A's original
timer-based `component_remount` attempts (a probabilistic test that
can pass or fail depending on timing luck, teaching little either way).
Fixed by switching to a monotonic `requestAnimationFrame` loop with no
easing and no rest points, matching Sprint 6A's own lesson that a
deterministic trigger beats a probabilistic one:

```
"... element is not stable\n    - retrying click action\n      - waiting 20ms\n    ... element is not stable ..."
```

### [Conclusion] Five actionability reasons and one resolution boundary, fully evidenced

| Signal | Evidence source | Message shape |
|---|---|---|
| Locator never resolved | Real `healing_decisions.log` entries (`click()` and `fill()`) | `waiting for locator("...")` — nothing further |
| `enabled` | Diagnostic (`fill()` on `disabled`) | `element is not enabled` |
| `visible` | Diagnostic (`fill()` on `display:none`) | `element is not visible` |
| `editable` | Diagnostic (`fill()` on `readonly`) | `element is not editable` |
| `stable` | Diagnostic (`click()` on rAF-animated element) | `element is not stable` |
| `receives events` | Diagnostic (`click()` under a transparent overlay) | `<blocking element> intercepts pointer events` |

Every row above is either real production data or a captured live
Playwright exception — none inferred from documentation alone. This
confirms, empirically rather than by reading Playwright's actionability
docs and assuming they map cleanly onto `NOT_VISIBLE`/`TIMEOUT_WAITING`,
that Playwright's own model is genuinely two-stage: first "did the
locator resolve at all," then — only if it did — "which specific
readiness check is it failing." See `docs/gaps.md` Gap #5 (updated) and
Gap #12 for the resulting scope note, and the "Current Sprint 6
implication" section there for the candidate tree shape this evidence
points toward.

### [Follow-up] Model shape is evidenced, not yet decided

Deliberately not resolved in this entry: whether `FailureType` gets
restructured into a `FailureCategory`/`ActionabilityReason` split (or
some other concrete shape), what happens to `HealingAction`'s already-
declared `WaitStrategy`/`VisibilityStrategy` split under such a model,
and how `DETACHED_FROM_DOM` (Gap #4, deprioritized but not removed) fits
alongside a new "locator resolved vs. not" boundary. `docs/gaps.md`
intentionally stops short of committing to an enum shape — the evidence
above answers "does Playwright's call log support this distinction"
(yes, clearly), not "exactly how should PhoenixQA's types model it."
That's a separate, upcoming decision, to be made deliberately rather
than folded into this diagnostic entry.

---

## Sprint 6B (decision) — `FailureCategory` + `ActionabilityReason` model adopted

### [Decision] The model, as decided

Following a review round on the draft proposal, the model below is
adopted as the target design for the classifier, `ContextCollector`,
`HealingAction`, and the prompt layer. Not yet implemented in code — see
the `[Follow-up]` at the end of this entry for what's still open before
it can be.

```python
class FailureCategory(Enum):
    LOCATOR_RESOLUTION = "locator_resolution"  # locator did not resolve in time
    ACTIONABILITY = "actionability"            # locator resolved, an actionability check failed
    REFERENCE = "reference"                    # was actionable, then lost mid-action (dormant — see below)

class ActionabilityReason(Enum):
    VISIBLE = "visible"
    ENABLED = "enabled"
    EDITABLE = "editable"
    STABLE = "stable"
    RECEIVES_EVENTS = "receives_events"

@dataclass(frozen=True)
class ClassifiedFailure:
    category: FailureCategory
    action: Optional[str] = None                          # "click" / "fill" / etc.
    locator_resolved: Optional[bool] = None
    actionability_reason: Optional[ActionabilityReason] = None
    blocking_element: Optional[str] = None                 # only meaningful for RECEIVES_EVENTS
    raw_message: str = ""                                  # full call log, always retained — see Gap below
```

`classify_playwright_error()` is replaced by a genuinely different
function, not a patched version of the old one —
`parse_playwright_call_log(error) -> ClassifiedFailure`. This is a
structural parser of the call log's shape (presence/absence of
`"locator resolved to"`, presence of `"attempting ... action"` plus a
specific `"element is not X"` line, or `"... intercepts pointer
events"`), not a substring check on the whole message. Named as a
distinct function rather than a modified one because the shift from
"does this string contain X" to "what is the structure of this
multi-line log" is a rewrite in kind, not a patch — same distinction
this file has drawn before for `HealingProposal → ProviderResult`
(Sprint 5).

### [Decision] `HealingAction` gains one merged type instead of two

`ActionabilityStrategy` replaces the two separately-declared
`WaitStrategy`/`VisibilityStrategy` from Sprint 6's original pre-coding
decision — one `HealingAction` subtype covering all five
`ActionabilityReason` values, carrying enough structure to say not just
*why* the action failed but *what kind of recovery* is being proposed:

```python
class ActionabilityStrategyKind(Enum):
    WAIT_AND_RETRY = "wait_and_retry"
    SCROLL_INTO_VIEW = "scroll_into_view"
    DISMISS_BLOCKER = "dismiss_blocker"
    FORCE_NOT_ALLOWED = "force_not_allowed"
    NO_SAFE_RECOVERY = "no_safe_recovery"

@dataclass
class ActionabilityStrategy(HealingAction):
    reason: ActionabilityReason
    strategy: ActionabilityStrategyKind
    suggested_wait_ms: Optional[int] = None
    blocking_element: Optional[str] = None
    explanation: Optional[str] = None
```

Reasoning for the added `strategy` field, beyond `reason` alone: a
single `ActionabilityReason` doesn't imply a single fix.
`VISIBLE` alone could plausibly mean "wait," "scroll into view," "expand
a collapsed section," or "dismiss an overlay" — collapsing all of these
into one implicit `suggested_wait_ms`-only shape (the original Sprint 6
sketch) would silently narrow every actionability heal to "just wait
longer," which is often wrong. `SelectorReplacement` and (dormant)
`RetryStrategy` are otherwise unchanged from Sprint 6's original
declaration.

### [Decision] `ContextCollector` gets three collectors, named after the category boundary, not the diagnosis

```
phoenix/collector/collectors/
├── locator_resolution_collector.py   # replaces selector_collector.py's exclusive claim to this path
├── actionability_collector.py        # one collector, all five reasons — see rationale below
└── reference_collector.py            # dormant, see REFERENCE decision below
```

`LocatorResolutionCollector`, not `SelectorCollector` — this is the one
naming correction carried over directly from Sprint 6B's own diagnostic
finding, not a stylistic preference. Sprint 6B's `async_delay` diagnostic
showed that "locator never resolved" has at least three plausible real
causes (selector genuinely changed, element conditionally not yet
mounted, application in an unexpected state) that Playwright's message
cannot distinguish between. Naming the category `SELECTOR` would have
silently re-encoded the exact assumption Sprint 6B's evidence just
weighed against: that an unresolved locator implies a selector problem,
which is only sometimes true. `LOCATOR_RESOLUTION` names the observation
(the locator didn't resolve) without presupposing the diagnosis.

`ActionabilityCollector` stays a single collector across all five
reasons, not five separate ones — the collection logic (grab
`blocking_element`'s context when `RECEIVES_EVENTS`, maybe two position
samples over time for `STABLE`) differs by *field*, not by needing a
structurally different gathering strategy per reason, unlike the
original four-way `FailureType` split where `SELECTOR_NOT_FOUND` and
`DETACHED_FROM_DOM` genuinely needed different data entirely.

### [Decision] `REFERENCE` stays in the model as a dormant category, not removed

`DETACHED_FROM_DOM`'s Sprint 6A deprioritization (Gap #4) raised the
question of whether keeping a third `FailureCategory` for something with
no active collector is worth the conceptual weight. Resolved: yes, keep
it, but explicitly dormant. `REFERENCE` is not the same thing as
`LOCATOR_RESOLUTION` (never resolved) or `ACTIONABILITY` (resolved, not
ready) — it names "was actionable, then lost mid-action," a genuinely
distinct failure shape even though Sprint 6A found it architecturally
rare for this project's `Locator`-based interaction pattern.
`ReferenceCollector` is declared but intentionally has no implementation
plan — no work is scheduled against it until a real `Locator`-based
reproduction or production case justifies it. This mirrors how
`FailureType`'s original four members were declared in Sprint 2 before
three of them had real strategies — declaring the shape without
building it is a repeated, deliberate pattern in this project, not new
here.

### [Decision] `HealingContext` gets flat fields, not a nested `ClassifiedFailure`

`ClassifiedFailure` is the classifier's own return type — internal to
the classify → collect handoff. `HealingContext` (read by
`decision_logger.py`, `safe_mode.py`'s terminal display, and eventually
the prompt layer) gains `category: FailureCategory` and
`actionability_reason: Optional[ActionabilityReason]` as direct fields,
replacing today's single `failure_type: FailureType`, rather than
embedding `ClassifiedFailure` as a nested object. Reasoning: every
existing reader of `HealingContext.failure_type` accesses it as a flat
field; nesting would mean every call site changes shape (`context.failure_type`
→ `context.classified.category`) instead of just changing the field's
type at the same access path (`context.failure_type` → `context.category`).
Consistent with how `HealingContext` has stayed a flat dataclass since
Sprint 0 rather than accumulating nested structure.

### [Decision] Breaking change internally, compatibility label in the log

No `FailureType`-shaped compatibility adapter is kept in the internal
model — `category`/`actionability_reason` fully replace `failure_type`
in `HealingContext`, `ContextCollector`, and everywhere else code reads
it. Reasoning, stated directly: `Healing History` (Sprint 7) and the
benchmark runner (Sprint 8) will persist whatever shape exists at the
time they're built — carrying the old, now-known-to-be-wrong
`FailureType` model forward "for compatibility" would let an
already-corrected mistake calcify into a database schema, which is a
much more expensive place to fix it than a Python dataclass today. Same
reasoning already applied once in this project to justify the Sprint 5
`HealingProposal → ProviderResult` change rather than accreting optional
fields onto the old shape.

`healing_decisions.log`, however, keeps a flat, human-readable label
alongside the new structured fields, specifically for log-reading and
the eventual Allure dashboard's grouping/filtering:

```json
{
  "failure_category": "actionability",
  "actionability_reason": "stable",
  "failure_label": "actionability:stable",
  "...": "..."
}
```

`failure_label` is a derived, denormalized convenience field
(`f"{category.value}:{reason.value}"` when a reason exists, else just
`category.value`) — not a second source of truth, not a revival of
`FailureType`. Existing log entries written under the old
`"failure_type"` key are left as historical record, unmigrated; no
retention/migration policy is defined for `healing_decisions.log`
regardless (see `docs/known-limitations.md`'s existing note on this).

### [Follow-up] Gap #13 (NEW) — the model is a text-log parser, not a stable API contract

Named explicitly, not left as an aside in prose: every signal
`parse_playwright_call_log()` depends on (`"locator resolved to"`,
`"attempting ... action"`, `"element is not X"`, `"... intercepts
pointer events"`) is Playwright's human-readable diagnostic text, not a
documented, versioned API. Nothing prevents a future Playwright release
from rewording any of these lines, and no compatibility guarantee exists
either way — this project has already found two of its own hand-crafted
message assumptions wrong (Sprint 4's `fill()` shape, Sprint 6B's
`click()` `SELECTOR_NOT_FOUND` shape) without Playwright changing
anything; a real Playwright version bump is at least as capable of
invalidating today's parser. Filed as **Gap #13** in `docs/gaps.md` —
mitigation is procedural, not a design fix that removes the risk:
`ClassifiedFailure.raw_message` always retains the full original call
log precisely so a parsing miss degrades to "unclassified, here's the
raw text" rather than a silent wrong answer, and any
`pip install --upgrade playwright` is worth a manual spot-check against
a live run, not just a green CI, until Playwright ships something more
structured (a documented candidate: filing feedback with Playwright
requesting structured actionability metadata on `TimeoutError`, noted
here as a future-ideas candidate, not a current action item).

### [Follow-up] Gap #14 (NEW) — `LocatorResolutionCollector` cannot yet distinguish *why* a locator never resolved

Named as a genuinely open problem, not solved by the rename above.
Renaming `SELECTOR` to `LOCATOR_RESOLUTION` correctly stops the category
name from presupposing "selector is broken" — but it doesn't give
`LocatorResolutionCollector` any actual way to tell apart the three
plausible causes Sprint 6B's `async_delay` diagnostic surfaced (selector
genuinely changed, element conditionally not yet mounted, application in
an unexpected state), because Playwright's message is identical in all
three cases (`"waiting for locator(...)"`, nothing further). Filed as
**Gap #14**. Not blocking adoption of the model above — `SelectorReplacement`
remains a reasonable default action for this category until a better
signal is found — but tracked explicitly so PhoenixQA doesn't quietly
"fix" a correct selector because the real cause was a conditionally-mounted
element with a too-aggressive test timeout, which Sprint 6B's own
`async_delay` investigation showed is a real, not hypothetical, risk. No
resolution proposed here; a plausible future direction (DOM polling
after the timeout fires, to see whether the element appears shortly
after, distinguishing "would have resolved given more time" from "never
would have") is noted as a candidate but not committed to.

### [Follow-up] What's still open before implementation can start

This entry decides the model shape; it does not implement it. Before
`phoenix/collector/collectors/locator_resolution_collector.py` and
`actionability_collector.py` get written, the same sequencing discipline
Sprint 6 committed to at the start (vertical slices, live verification
before declaring a sub-sprint done) still applies — classifier rewrite
first, verified against real captured call logs (already have five of
six actionability reasons' real shapes from Sprint 6B; `REFERENCE`
intentionally has none, by design), before collector or prompt work
begins.

---

## TODO (future sprints)
- Future sprint (not yet assigned): decide whether is_visible()/get_text() should support healing=True at all, and what "healing" means for a boolean-returning assertion vs an action — surfaced by test_invalid_credentials failing on MSG_ERROR despite successful click/fill healing elsewhere in the same test
- Sprint 1: implement CHAOS_LEVELS as dict (LOW/MEDIUM/HIGH, level → mechanism list), not count-based
- Sprint 1: shadow_dom is an independent flag (SHADOW_DOM_ENABLED), not part of CHAOS_LEVELS — combinable with any level
- Sprint 1: dom_mutation.py gets most internal variants (wrap/retag/nest/reorder) — highest realism mechanism
- Sprint 1: implement `get_mechanisms_for_level()` helper — returns level's mechanism list only; shadow_dom checked separately
- Sprint 1: parametrize chaos tests by `chaos_level` AND `shadow_dom_enabled` from the start — avoids rewriting tests in Sprint 7
- Sprint 2: implement FailureType classification (classify_playwright_error) as the entry point to Context Collector — even though only SELECTOR_NOT_FOUND gets a full strategy this sprint, the routing structure must exist now
- Sprint 2: implement weighted semantic scoring (tokenize broken_selector, score DOM elements by data-testid/aria-label/name/placeholder/id/textContent with weights 5/4/4/3/2/1), THEN closest(form/section) from best candidate, THEN shadow DOM check — not naive "first visible landmark"
- Sprint 3: replace outerHTML re-matching with stored ElementHandle / unique ancestor path — identical elements currently collide
- Sprint 3 or its own sprint (REQUIRED, not optional): implement DETACHED_FROM_DOM context-gathering strategy — most common real-world Salesforce/Lightning-style failure per hands-on experience. **Update (Sprint 6A): deprioritized after a controlled experiment found no reproduction against this project's Locator-based interaction pattern across 4 escalating attempts — see "Sprint 6A conclusion" above. Not proven impossible, not resolved — superseded in priority by the NOT_VISIBLE/TIMEOUT_WAITING TODO below.**
- Sprint 3 or its own sprint (REQUIRED, not optional): implement NOT_VISIBLE and TIMEOUT_WAITING strategies
- Future: Chaos App needs a new mechanism simulating component remount / detach-mid-action to actually test DETACHED_FROM_DOM handling — doesn't exist yet in current 4 mechanisms. **Update (Sprint 6A): built (`componentRemount.jsx`) and tested across 4 escalating configurations — did not reproduce the target failure against this project's Locator-based interactions. See "Sprint 6A conclusion" above.**
- Before Sprint 6: resolve "healing correctness" definition (test passing ≠ fix is correct) before designing Healing History schema
- Sprint 3: prompt template for selector healing — include element role, aria, surrounding context
- Sprint 6: SQLite schema design — index by page_url + broken_selector for fast few-shot lookup
- Sprint 6: revisit "baseline snapshot on green tests" brainstorm — extend history_store.py, not a new component; needs retention strategy before implementing
- Sprint 7 (renamed: "Healing Benchmark Runner" — name now matches what it actually does): iterate CHAOS_LEVELS × shadow_dom flag (two dimensions), call get_mechanisms_for_level(), run suite, log pass rate per combination. Few-shot self-training stays in scope as a sub-component, not the headline.
- Sprint 7/8: implement `HeuristicProvider` (phoenix/ai/heuristic_provider.py) — fuzzy/Levenshtein selector matching, zero LLM calls, same BaseProvider interface — REQUIRED so benchmark proves LLM is actually adding value, not just "healing exists". Treat as an experimental control, not a third user-facing mode — always report its number alongside the LLM number in any write-up, never the LLM number alone
- Sprint 5: DONE — implemented max_attempts_total, token budget (input/output, not dollar cost), max_time_per_heal_ms via AutonomousPolicy/HealingBudget — no infinite retry loops in CI
- Sprint 3: decide whether screenshot is actually part of v1 LLM prompt (multimodal) or explicitly deferred — currently declared in HealingContext but has had zero design attention
- Sprint 6/7/8: dedicated pass on cost accounting — prompt token budgets, DOM snapshot storage size limits, history_store.py retention policy, benchmark wall-clock runtime budget — premature to size now, revisit once real numbers exist from Sprint 3/4
- Sprint 3/4: revisit context_collector.py's multiple page.evaluate() round-trips (up to 4 per failure) once real cost/timing data exists — premature to optimize now
- Sprint 5: DONE — verified Autonomous Mode against real Chaos App + Ollama with HEALING_MODE=autonomous. Confirmed min_confidence=0.75 auto-accepts good proposals (0.85-0.95) and auto-rejects bad ones (0.0, truncated JSON), zero terminal prompts either way
- Sprint 6 (NEW, pre-coding decision): `ContextCollector` becomes a router over `BaseContextCollector` subclasses (`phoenix/collector/collectors/`) — one per FailureType — instead of an if/elif ladder. `SELECTOR_NOT_FOUND` logic moves into `selector_collector.py` unchanged; this is a pure refactor with no behavior change for the existing path
- Sprint 6 (NEW, pre-coding decision): `prompt_templates.py` splits into `phoenix/ai/prompts/` with one module per FailureType (`selector_prompt.py`, `detached_prompt.py`, ...), routed via a small `get_prompt_for(failure_type)` function
- Sprint 6 (NEW, pre-coding decision, BLOCKING): introduce `HealingAction` ABC hierarchy (`SelectorReplacement`, `RetryStrategy`, `WaitStrategy`, `VisibilityStrategy`) to replace `HealingProposal` as the universal provider return shape. `ProviderResult.proposal` → `ProviderResult.action`. Requires updating `Healer`, `safe_mode.py`, `decision_logger.py`, and `response_parser.py`'s fallback path — same breadth as Sprint 5's HealingProposal→ProviderResult refactor
- Sprint 6A: DONE — `componentRemount.jsx` (`RemountTrigger.TIMEOUT` and `RemountTrigger.MOUSEDOWN`, single-component remount on LoginForm's submit button, independent `COMPONENT_REMOUNT_ENABLED` flag) + classifier extended to recognize `DETACHED_FROM_DOM` via substring match, checked before the generic SELECTOR_NOT_FOUND check. Live verification across 4 escalating configurations (200-800ms → 100-300ms → 10-30ms → deterministic mousedown) found no reproduction — deprioritized as a target failure type for this project's Locator-based interaction pattern, not proven impossible in general. See "Sprint 6A conclusion."
- Sprint 6A live run: DONE — fixed `BasePage.click()`/`fill()` not catching `HealingRejectedError`/`HealingLimitExceededError`/`HealingFailedError` and re-raising the original Playwright error, per `healer.py`'s documented (but previously unimplemented) contract. 6 new regression tests in `tests/unit/test_base_page.py`. Unrelated to `DETACHED_FROM_DOM` — found incidentally while attempting to verify Sprint 6A live
- Sprint 6B/C/D as originally scoped (`DetachedFromDomCollector`, `detached_prompt.py`, `RetryStrategy` end-to-end): PAUSED — see "Sprint 6A conclusion" above. Four escalating reproduction attempts found no `DETACHED_FROM_DOM` against this project's Locator-based interaction pattern; consistent with Playwright's documented auto-retry behavior on mid-action detachment, not confirmed as a mechanism deficiency in `componentRemount.jsx`
- Sprint 6B pre-coding diagnostics: DONE — five actionability reasons (`visible`/`enabled`/`editable`/`stable`/`receives events`) and the locator-resolution boundary confirmed empirically via real production logs plus six throwaway diagnostic tests. Superseded the plan to simply "choose NOT_VISIBLE or TIMEOUT_WAITING" — evidence points toward a two-stage model (selector resolution vs. actionability reason) rather than a flat choice between the two original enum members. See `LEARNINGS.md` Sprint 6B and `docs/gaps.md` Gap #5/#12
- Sprint 6B model decision: DONE — `FailureCategory` (`LOCATOR_RESOLUTION`/`ACTIONABILITY`/`REFERENCE`) + `ActionabilityReason` (5 values) + `ClassifiedFailure` adopted as the target design, replacing the flat `FailureType` enum internally. `HealingContext` gains `category`/`actionability_reason` flat fields; `HealingAction` gains one merged `ActionabilityStrategy` (with a `strategy: ActionabilityStrategyKind` field) replacing the separately-declared `WaitStrategy`/`VisibilityStrategy`. `ContextCollector` becomes three collectors (`locator_resolution_collector.py`, `actionability_collector.py`, `reference_collector.py`, the last dormant). See `LEARNINGS.md` "Sprint 6B (decision)"
- Sprint 6B implementation (NOT started): `classify_playwright_error()` → `parse_playwright_call_log()` rewrite is the first concrete step, verified against real captured call logs before collector/prompt work begins — same vertical-slice discipline as Sprint 6's original 6A-6D plan
- Gap #13 (NEW): the whole model depends on Playwright's human-readable diagnostic text, not a documented API — `ClassifiedFailure.raw_message` always retains the full call log as a mitigation, and a Playwright version bump deserves a manual spot-check, not just green CI, until something more structured exists
- Gap #14 (NEW): `LocatorResolutionCollector` still cannot distinguish *why* a locator never resolved (genuine selector drift vs. conditionally-not-yet-mounted element vs. wrong app state) — Playwright's message is identical in all three cases. Not blocking the model's adoption; `SelectorReplacement` stays the default action for this category until a better signal is found
- Decisions #1-4 from Sprint 6 pre-coding (action-recovery reframing, polymorphic `ContextCollector`, split prompts, `HealingAction` hierarchy) are UNAFFECTED by the redirect — they generalize across failure types, not specifically around `DETACHED_FROM_DOM`