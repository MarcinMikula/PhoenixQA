/**
 * componentRemount.jsx
 *
 * Realism: simulates a framework re-rendering a component and replacing
 * its DOM node mid-lifecycle — e.g. Salesforce Lightning re-rendering a
 * component between when a test locates an element and when it finishes
 * acting on it. This is NOT the same failure mode as selector_rotation:
 * the identifying attribute (data-testid) can stay IDENTICAL across a
 * remount — what changes is the underlying DOM NODE itself. A Playwright
 * locator re-queries by selector on every actionability retry, so it
 * will find the new node fine on the NEXT check. The failure only shows
 * up if the OLD node was detached mid-action (e.g. mid-click) — exactly
 * the DETACHED_FROM_DOM failure type PhoenixQA classifies separately
 * from SELECTOR_NOT_FOUND (see LEARNINGS.md Gap #4, Gap #12).
 *
 * ARCHITECTURE (see LEARNINGS.md "Sprint 6 (pre-coding)" and the direct
 * design discussion that shaped this file): remounts have different
 * real-world CAUSES, not just one generic "chaos timer":
 *
 *   RemountTrigger.TIMEOUT           - a periodic re-render unrelated to
 *                                       user interaction (e.g. a polling
 *                                       subscription re-render). IMPLEMENTED.
 *   RemountTrigger.STATE_CHANGE      - typing -> validation -> re-render.
 *                                       NOT YET IMPLEMENTED — future sprint.
 *   RemountTrigger.NETWORK_RESPONSE  - click -> fetch() -> response ->
 *                                       component recreated. Likely the
 *                                       second most common enterprise
 *                                       case. NOT YET IMPLEMENTED — future
 *                                       sprint.
 *
 * Sprint 6A implements ONLY TIMEOUT — same "prove one variant fully
 * before generalizing" instinct as every other phased rollout in this
 * project (FailureType in Sprint 2, chaos levels in Sprint 1). The enum
 * declares all three now so STATE_CHANGE/NETWORK_RESPONSE don't require
 * reshaping this file later — mirroring how FailureType declared all
 * four of its values in Sprint 2 while only implementing one.
 *
 * Whether the Healer's eventual behavior actually needs to differ by
 * trigger (Gap #12 territory: does a network-response-caused detachment
 * need a different recovery strategy than a timer-caused one?) is an
 * open question for the sprint that implements STATE_CHANGE/
 * NETWORK_RESPONSE — not decided here. This file only needs the
 * mechanism to reliably PRODUCE each kind of failure; whether the
 * healing side cares about "why" is a later sprint's problem.
 *
 * SCOPE — only ONE component is remounted, not a whole form. Real
 * frameworks (React reconciliation, Lightning) rarely blow away an
 * entire subtree; they replace one component at a time while its
 * siblings stay untouched. Wrapping an entire <form> would be a cruder,
 * less realistic simulation — see direct design discussion that shaped
 * this file.
 */
import { useEffect, useState, cloneElement } from 'react'

export const RemountTrigger = {
  TIMEOUT: 'timeout',
  STATE_CHANGE: 'state_change', // NOT YET IMPLEMENTED — future sprint
  NETWORK_RESPONSE: 'network_response', // NOT YET IMPLEMENTED — future sprint
}

// Same order of magnitude as asyncDelay.js's randomDelayMs (300-2000ms) —
// deliberately kept in a similar "feels like real timing jitter, not a
// stopwatch-precise interval" range, but on the shorter end since this
// needs to repeat and realistically collide with an in-flight Playwright
// action within a normal test timeout window.
const MIN_DELAY_MS = 200
const MAX_DELAY_MS = 800

function randomDelayMs() {
  return MIN_DELAY_MS + Math.floor(Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS))
}

/**
 * Wraps a SINGLE child element. While `active`, repeatedly forces React
 * to unmount and remount that child as a genuinely new DOM node — not
 * just a re-render — by changing its `key` prop on an interval. React
 * treats a key change as "this is a different element," tearing down
 * the old DOM node and creating a brand new one. That distinction is
 * the whole point: a plain re-render (same node, updated attributes)
 * would NOT reproduce DETACHED_FROM_DOM — only a genuine node
 * replacement does, because only that leaves a Playwright action that
 * was holding a reference to the OLD node with nothing to act on.
 *
 * Repeats on an interval for as long as `active` is true, rather than
 * remounting once — a single remount would only rarely collide with an
 * in-flight Playwright action. A repeating remount is both more
 * realistic (real re-render loops recur, they aren't one-off) and gives
 * the Chaos App a meaningfully higher chance of actually producing the
 * failure it exists to simulate within a normal test run.
 *
 * Usage:
 *   <ComponentRemountWrapper active={mechanismActive} trigger={RemountTrigger.TIMEOUT}>
 *     <button data-testid={testIds.submit}>Log in</button>
 *   </ComponentRemountWrapper>
 *
 * IMPORTANT: wrap exactly one element, not a fragment of several — see
 * module docstring on why this stays scoped to a single component
 * rather than an entire form.
 */
export function ComponentRemountWrapper({ active, trigger = RemountTrigger.TIMEOUT, children }) {
  const [remountKey, setRemountKey] = useState(0)

  useEffect(() => {
    if (!active) return

    if (trigger !== RemountTrigger.TIMEOUT) {
      // Explicit and loud, matching the Python-side convention of
      // NotImplementedError placeholders (see failure_classifier.py,
      // context_collector.py) rather than silently no-op'ing into a
      // trigger that looks configured but does nothing.
      throw new Error(
        `ComponentRemountWrapper: trigger "${trigger}" is not implemented yet. ` +
          'Only RemountTrigger.TIMEOUT is built (Sprint 6A). ' +
          'STATE_CHANGE and NETWORK_RESPONSE are declared but not implemented — see LEARNINGS.md.'
      )
    }

    let cancelled = false
    let timeoutId

    function scheduleRemount() {
      timeoutId = setTimeout(() => {
        if (cancelled) return
        setRemountKey((k) => k + 1)
        scheduleRemount() // repeat — see docstring on why this isn't one-shot
      }, randomDelayMs())
    }

    scheduleRemount()

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [active, trigger])

  if (!active) {
    return children
  }

  // key change forces React to unmount the old DOM node and mount a
  // genuinely new one, rather than patching the existing node in place.
  return cloneElement(children, { key: remountKey })
}