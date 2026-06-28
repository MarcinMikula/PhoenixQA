# Future ideas — thematic index

Brainstormed possibilities deliberately NOT in current scope — recorded
so they aren't lost, each with a note on when/whether to revisit. **Full
reasoning lives in `LEARNINGS.md`** — this file is a map, not a copy.

## Historical fingerprinting (baseline snapshot on green tests)

Idea: instead of only collecting context reactively when a test FAILS,
also snapshot the locator + its DOM context whenever a test PASSES. This
would give the Healer a historical "last known good" reference to diff
against, instead of reconstructing context from scratch at failure time
only — a diff-based signal ("this used to point to X, now there's a
structurally similar element with a different suffix") is potentially
stronger than guessing purely from the current DOM.

**Why not now:** changes `BasePage` from "healing is opt-in at failure"
to "logging is always-on for every test run." Also needs a retention
strategy before the history database grows unboundedly.

**Why it's not wasted scope creep:** it's a natural extension of
`history_store.py` (Sprint 6), which already exists to store healing
decisions — not a fourth independent system.

**Important clarification (resolved in follow-up discussion):** this is
NOT a prerequisite for the Gap #9 heuristic-vs-LLM benchmark. The
heuristic baseline anchors on the PRESENT (the broken selector's own
name vs. the current DOM), not the past — fully buildable without
fingerprinting. Fingerprinting, if pursued, would be a fourth benchmark
column or a modifier on the existing two, not a foundation for them.

**Revisit:** Sprint 6, alongside `history_store.py` design. Don't
implement Approach B (fingerprint-augmented healing) until Approach A
(current DOM-only healing) has a benchmark baseline to compare against —
measure before adding complexity, not the other way around.

## Additional chaos mechanisms beyond the current four

Mentioned as a reason CHAOS_LEVELS was designed as a dict rather than a
count: future mechanisms like `A11Y_NOISE` (accessibility-tree
disruption), `LOCALE_SWITCH` (i18n string changes breaking
text-based selectors), or `FEATURE_FLAGS` (conditionally-rendered UI)
are plausible additions that the current architecture already
accommodates without restructuring.

**Revisit:** opportunistically, whenever a real-world failure mode
suggests one of these would be a valuable addition to the benchmark
matrix. Not currently scheduled into any sprint.

## Component remount / detach-mid-action mechanism for Chaos App

Needed to actually exercise `FailureType.DETACHED_FROM_DOM` handling —
see Gap #4 in `docs/gaps.md`. Concrete spec already drafted: a wrapper
component (`componentRemount.jsx`) that genuinely unmounts and
re-mounts a target element as a new DOM node (not just a re-render) on
interaction or after a delay, mirroring what frameworks like Salesforce
Lightning do during a re-render.

**Revisit:** Sprint 6 (Failure type expansion), required scope — not
optional. Also worth closing out alongside this: explicitly documenting
that `asyncDelay.js`'s invisible→visible transition already provides
partial, currently-undocumented coverage for `NOT_VISIBLE`.

## Multimodal healing context (screenshots)

`defect-pilot`'s `OllamaProvider.complete_with_images()` pattern (raw
base64 in the `images` field) is already a usable reference if/when
PhoenixQA decides to send screenshots to a vision-capable model
(`llava`) alongside or instead of the DOM snapshot.

**Revisit:** Sprint 3 decision point flagged but not resolved — see Gap
#8 in `docs/gaps.md`. Most relevant for failure types where the DOM
alone doesn't explain the problem (e.g. an element rendering off-screen
or visually obscured despite being "visible" in the DOM sense).

## Richer decision log fields

Small bucket (safe anytime): `provider`, `elapsed_ms`, `input_tokens`,
`output_tokens`, `attempt` — all already computed in memory (`ProviderResult`,
`HealingBudget`) when `log_decision()` is called, just not currently
passed through to the log. Pure wiring, no new logic.

Larger bucket (deliberately deferred): replacing the bare `accepted: bool`
field with a richer `decision` enum (`AUTO_APPLIED`/`AUTO_REJECTED`/
`HUMAN_APPROVED`/`HUMAN_REJECTED`) — today `accepted: false` conflates
three different stories into one boolean. Worth designing once,
deliberately, alongside Sprint 6/7's `history_store.py` schema.

**Revisit:** small bucket — anytime, low risk. Larger bucket — Sprint 6/7,
alongside Gap #1 (healing correctness) resolution.

## Allure Healing Dashboard (replaces the "pile of screenshots" demo plan)

One dashboard — success rate, healing timeline, confidence distribution,
top repaired selectors, failure reasons, budget usage, provider
comparison — communicates more than scattered terminal screenshots.
Directly depends on the richer log fields above (budget usage and
provider comparison widgets need `elapsed_ms`/tokens/`provider` to render
real data, not placeholders).

**Revisit:** Sprint 9 (reporting), after Sprint 6/7/8 (history + benchmark
runner) produce real data for it to visualize. Sequencing matters here —
building the dashboard before the data pipeline exists means it ships
with fake numbers.

## Where to read more
Search `LEARNINGS.md` for "Future consideration" or the bolded idea name
above for the full brainstorm, rejected alternatives, and any code
sketches.