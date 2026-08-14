/**
 * visibilityDelay.jsx
 *
 * Fourth independent chaos mechanism (same pattern as shadow_dom,
 * component_remount, pointer_events_overlay — not part of CHAOS_LEVELS),
 * simulating ActionabilityReason.VISIBLE. Unlike RECEIVES_EVENTS, this
 * failure has no separate "blocking element" — Playwright's own message
 * for this reason is just "element is not visible," naming nothing else
 * (confirmed against the real captured call log in
 * tests/unit/test_failure_classifier.py). The evidence has to be about
 * the TARGET element itself.
 *
 * TWO MODES, deliberately, per direct discussion — this is the first
 * Chaos App mechanism built specifically to test BOTH directions of a
 * policy guardrail live, not just one:
 *   - PERMANENT: the element never becomes visible. Ground truth:
 *     no_safe_recovery. Mirrors pointerEventsOverlay.jsx's design
 *     exactly (Sprint 6B, RECEIVES_EVENTS) — a case with no positive
 *     evidence of recovery, for testing that the policy correctly
 *     BLOCKS an unsafe wait_and_retry proposal.
 *   - TRANSIENT: the element genuinely becomes visible after delayMs.
 *     Ground truth: wait_and_retry. The first Chaos App case built
 *     specifically to test that the policy correctly ALLOWS a
 *     wait_and_retry proposal when real evidence supports it —
 *     something Sprint 6B's RECEIVES_EVENTS investigation only ever
 *     exercised in mocked unit tests, never live.
 *
 * EVIDENCE DESIGN — deliberately reuses the exact CSS evidence fields
 * ActionabilityCollector/actionability_policy.py already read for
 * RECEIVES_EVENTS (animationName/transitionProperty in computed style),
 * rather than inventing a new evidence shape for this reason. In
 * TRANSIENT mode, the element's inline style genuinely declares
 * `transitionProperty: 'visibility'` and a real `transitionDuration`
 * for the FULL duration it stays hidden — a real, static CSS fact
 * visible in computed style from the moment the element mounts, not
 * fabricated after the fact to match what the collector expects to
 * see. The actual visibility flip is driven by a real setTimeout, so
 * the element genuinely becomes visible when the delay elapses — this
 * is real behavior, not just a label. In PERMANENT mode, no
 * transition-property is declared at all, so computed style reports
 * the browser's own default ("all" for transition-property, "none" for
 * animation-name — see actionability_policy.py's own comments on why
 * these two defaults differ) — genuinely zero evidence, not simulated
 * absence of it.
 */
import { cloneElement, useEffect, useState } from 'react'

export const VisibilityDelayMode = {
  OFF: 'off',
  PERMANENT: 'permanent',
  TRANSIENT: 'transient',
}

/**
 * Wraps a single child (must accept a `style` prop — used here on the
 * password <input>, not the login button already occupied by
 * componentRemount/pointerEventsOverlay) and controls its visibility
 * per `mode`. children remain otherwise completely unmodified — same
 * selector, same DOM position, same tag — only the `style` prop is
 * merged in.
 *
 * Usage:
 *   <VisibilityDelayWrapper mode={visibilityDelayMode} delayMs={visibilityDelayMs}>
 *     <input data-testid="password" ... />
 *   </VisibilityDelayWrapper>
 */
export function VisibilityDelayWrapper({ mode, delayMs = 1000, children }) {
  const [hidden, setHidden] = useState(mode !== VisibilityDelayMode.OFF)

  useEffect(() => {
    if (mode === VisibilityDelayMode.TRANSIENT) {
      setHidden(true)
      const id = setTimeout(() => setHidden(false), delayMs)
      return () => clearTimeout(id)
    }
    setHidden(mode === VisibilityDelayMode.PERMANENT)
  }, [mode, delayMs])

  if (mode === VisibilityDelayMode.OFF) {
    return children
  }

  if (!hidden) {
    return children
  }

  const style =
    mode === VisibilityDelayMode.TRANSIENT
      ? {
          visibility: 'hidden',
          transitionProperty: 'visibility',
          transitionDuration: `${delayMs}ms`,
        }
      : { visibility: 'hidden' }

  return cloneElement(children, {
    style: { ...children.props.style, ...style },
  })
}
