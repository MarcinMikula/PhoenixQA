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
- Sprint 3 or its own sprint (REQUIRED, not optional): implement DETACHED_FROM_DOM context-gathering strategy — most common real-world Salesforce/Lightning-style failure per hands-on experience
- Sprint 3 or its own sprint (REQUIRED, not optional): implement NOT_VISIBLE and TIMEOUT_WAITING strategies
- Future: Chaos App needs a new mechanism simulating component remount / detach-mid-action to actually test DETACHED_FROM_DOM handling — doesn't exist yet in current 4 mechanisms
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