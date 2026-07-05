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
 *                                       Probabilistic — realistic for
 *                                       general/background chaos use, but
 *                                       whether it collides with any given
 *                                       Playwright action within a test
 *                                       timeout is down to timing luck.
 *   RemountTrigger.MOUSEDOWN         - remounts SYNCHRONOUSLY the instant
 *                                       the wrapped element receives a
 *                                       native mousedown event. IMPLEMENTED
 *                                       (Sprint 6A live-verification
 *                                       addition — see LEARNINGS.md
 *                                       "Sprint 6A — deterministic
 *                                       MOUSEDOWN trigger"). Deterministic,
 *                                       not probabilistic: instead of
 *                                       asking "will a random timer ever
 *                                       collide with a click?", this asks
 *                                       "what happens if the element is
 *                                       replaced at the EXACT moment an
 *                                       interaction begins?" — isolating
 *                                       the one variable that actually
 *                                       matters for verifying
 *                                       DETACHED_FROM_DOM classification,
 *                                       the same "isolate one variable"
 *                                       instinct behind Shadow DOM's
 *                                       decoupling (Sprint 1) and the
 *                                       mechanism-override design (Sprint
 *                                       6A). Intended as a VERIFICATION
 *                                       tool primarily, though it may also
 *                                       be a reasonable "worst case"
 *                                       background mechanism later.
 *   RemountTrigger.STATE_CHANGE      - typing -> validation -> re-render.
 *                                       NOT YET IMPLEMENTED — future sprint.
 *   RemountTrigger.NETWORK_RESPONSE  - click -> fetch() -> response ->
 *                                       component recreated. Likely the
 *                                       second most common enterprise
 *                                       case. NOT YET IMPLEMENTED — future
 *                                       sprint.
 *
 * Sprint 6A implements TIMEOUT and MOUSEDOWN — same "prove one variant
 * fully before generalizing" instinct as every other phased rollout in
 * this project (FailureType in Sprint 2, chaos levels in Sprint 1). The
 * enum declares all four now so STATE_CHANGE/NETWORK_RESPONSE don't
 * require reshaping this file later.
 *
 * Whether the Healer's eventual behavior actually needs to differ by
 * trigger (Gap #12 territory) is an open question for a later sprint —
 * not decided here. This file only needs the mechanism to reliably
 * PRODUCE each kind of failure (or to honestly demonstrate that it
 * cannot, which is itself a real finding — see LEARNINGS.md); whether
 * the healing side cares about "why" is a separate question.
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
  MOUSEDOWN: 'mousedown',
  STATE_CHANGE: 'state_change', // NOT YET IMPLEMENTED — future sprint
  NETWORK_RESPONSE: 'network_response', // NOT YET IMPLEMENTED — future sprint
}

const IMPLEMENTED_TRIGGERS = [RemountTrigger.TIMEOUT, RemountTrigger.MOUSEDOWN]

// Same order of magnitude as asyncDelay.js's randomDelayMs (300-2000ms) —
// deliberately kept in a similar "feels like real timing jitter, not a
// stopwatch-precise interval" range, but on the shorter end since this
// needs to repeat and realistically collide with an in-flight Playwright
// action within a normal test timeout window. These are the REALISTIC
// defaults for RemountTrigger.TIMEOUT only — see the `minDelayMs`/
// `maxDelayMs` props below for why a caller might deliberately want
// something tighter during verification. Irrelevant to
// RemountTrigger.MOUSEDOWN, which has no interval at all.
const DEFAULT_MIN_DELAY_MS = 200
const DEFAULT_MAX_DELAY_MS = 800

function randomDelayMs(minMs, maxMs) {
  return minMs + Math.floor(Math.random() * (maxMs - minMs))
}

/**
 * Wraps a SINGLE child element. While `active`, forces React to unmount
 * and remount that child as a genuinely new DOM node — not just a
 * re-render — by changing its `key` prop. React treats a key change as
 * "this is a different element," tearing down the old DOM node and
 * creating a brand new one. That distinction is the whole point: a
 * plain re-render (same node, updated attributes) would NOT reproduce
 * DETACHED_FROM_DOM — only a genuine node replacement does, because only
 * that leaves a Playwright action that was holding a reference to the
 * OLD node with nothing to act on.
 *
 * Usage (background/realistic, probabilistic):
 *   <ComponentRemountWrapper active={mechanismActive} trigger={RemountTrigger.TIMEOUT}>
 *     <button data-testid={testIds.submit}>Log in</button>
 *   </ComponentRemountWrapper>
 *
 * Usage (deterministic verification):
 *   <ComponentRemountWrapper active={mechanismActive} trigger={RemountTrigger.MOUSEDOWN}>
 *     <button data-testid={testIds.submit}>Log in</button>
 *   </ComponentRemountWrapper>
 *
 * RemountTrigger.TIMEOUT repeats on a random interval for as long as
 * `active` is true. `minDelayMs`/`maxDelayMs` (optional, default to the
 * realistic 200-800ms range above) let a caller tighten that interval
 * for verification purposes — see LEARNINGS.md "Sprint 6A live
 * verification" for why this knob exists, and for why a purely
 * probabilistic approach (however short the interval) was ultimately
 * set aside in favor of RemountTrigger.MOUSEDOWN for actually verifying
 * DETACHED_FROM_DOM classification.
 *
 * RemountTrigger.MOUSEDOWN has no interval — it attaches a native
 * `mousedown` handler to the wrapped element and bumps the remount key
 * SYNCHRONOUSLY the instant that event fires. React 18 flushes discrete
 * event updates (mousedown is one) before the browser dispatches the
 * NEXT native event in the same user gesture (mouseup, click) — so by
 * the time Playwright's click sequence reaches mouseup/click, the OLD
 * DOM node should already be torn down and a new one mounted in its
 * place. Deterministic: no timing luck involved in WHETHER a remount
 * happens during the action, only in what Playwright/the browser then
 * does about it — which is exactly the question worth answering.
 *
 * IMPORTANT: wrap exactly one element, not a fragment of several — see
 * module docstring on why this stays scoped to a single component
 * rather than an entire form.
 */
export function ComponentRemountWrapper({
  active,
  trigger = RemountTrigger.TIMEOUT,
  minDelayMs = DEFAULT_MIN_DELAY_MS,
  maxDelayMs = DEFAULT_MAX_DELAY_MS,
  children,
}) {
  const [remountKey, setRemountKey] = useState(0)

  useEffect(() => {
    if (!active) return

    if (!IMPLEMENTED_TRIGGERS.includes(trigger)) {
      // Explicit and loud, matching the Python-side convention of
      // NotImplementedError placeholders (see failure_classifier.py,
      // context_collector.py) rather than silently no-op'ing into a
      // trigger that looks configured but does nothing.
      throw new Error(
        `ComponentRemountWrapper: trigger "${trigger}" is not implemented yet. ` +
          'RemountTrigger.TIMEOUT and RemountTrigger.MOUSEDOWN are built (Sprint 6A). ' +
          'STATE_CHANGE and NETWORK_RESPONSE are declared but not implemented — see LEARNINGS.md.'
      )
    }

    if (trigger !== RemountTrigger.TIMEOUT) {
      // RemountTrigger.MOUSEDOWN needs no interval/timer setup at all —
      // it's wired directly onto the cloned element below, driven by a
      // real DOM event rather than a schedule.
      return
    }

    let cancelled = false
    let timeoutId

    function scheduleRemount() {
      timeoutId = setTimeout(() => {
        if (cancelled) return
        setRemountKey((k) => k + 1)
        scheduleRemount() // repeat — a single remount would too rarely
        // collide with an in-flight action; see module docstring.
      }, randomDelayMs(minDelayMs, maxDelayMs))
    }

    scheduleRemount()

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [active, trigger, minDelayMs, maxDelayMs])

  if (!active) {
    return children
  }

  if (trigger === RemountTrigger.MOUSEDOWN) {
    // Preserve any onMouseDown the wrapped element already declares
    // (none of Chaos App's current components do, but this keeps the
    // wrapper composable rather than silently dropping a handler a
    // future component might add).
    const existingOnMouseDown = children.props.onMouseDown
    const handleMouseDown = (event) => {
      if (existingOnMouseDown) existingOnMouseDown(event)
      setRemountKey((k) => k + 1)
    }
    return cloneElement(children, { key: remountKey, onMouseDown: handleMouseDown })
  }

  // RemountTrigger.TIMEOUT (default) — key change alone; the interval
  // effect above drives when it changes.
  return cloneElement(children, { key: remountKey })
}