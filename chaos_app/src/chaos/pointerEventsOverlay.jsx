/**
 * pointerEventsOverlay.jsx
 *
 * Independent chaos mechanism (same pattern as shadow_dom and
 * component_remount — not part of CHAOS_LEVELS), simulating
 * ActionabilityReason.RECEIVES_EVENTS: a transparent element covering
 * the whole viewport, intercepting pointer events before they reach
 * whatever's underneath. Common real-world causes: cookie banners,
 * modals, sticky headers, loading overlays, backdrops left behind by a
 * closed dialog.
 *
 * TWO MODES, added per direct discussion (Sprint 8) — mirrors
 * visibilityDelay.jsx's PERMANENT/TRANSIENT split exactly, extended
 * to this mechanism once VISIBLE's own two-directional live
 * verification (Sprint 6B/8) proved the pattern worth reusing rather
 * than reinventing per mechanism:
 *   - PERMANENT (the ONLY mode this file originally had): the overlay
 *     never goes away. Ground truth: no_safe_recovery. No
 *     animation/transition declared — genuinely zero evidence, not
 *     simulated absence of it (same principle as visibilityDelay.jsx's
 *     PERMANENT mode).
 *   - TRANSIENT: the overlay genuinely stops intercepting pointer
 *     events after delayMs — unmounted outright, not merely faded
 *     visually, so a retried click genuinely reaches the button
 *     underneath. Ground truth: wait_and_retry. While present, its
 *     inline style declares a real `transitionProperty`/`transitionDuration`
 *     for the FULL duration it exists — the exact evidence shape
 *     actionability_policy.py's `_has_positive_transient_evidence()`
 *     checks (`transitionProperty` present and not the browser default
 *     `"all"`/`"none"`) — a real, static CSS fact visible in computed
 *     style from the moment the overlay mounts, not fabricated after
 *     the fact to match what the collector expects to see.
 *
 * Deterministic within each mode, same discipline as before (Sprint 6A's
 * move away from timer-based component remount toward a mousedown
 * trigger was about avoiding non-determinism in WHEN a chaos event
 * fires; TRANSIENT's setTimeout here is about a genuinely time-based
 * RECOVERY, the same category of thing visibilityDelay.jsx's TRANSIENT
 * mode already does, not a regression to the pattern Sprint 6A moved
 * away from).
 *
 * Deliberately NOT the same failure as NOT_VISIBLE or ENABLED — the
 * target element stays fully visible, enabled, and stable; only
 * pointer events are intercepted. Keeping this mechanism separate from
 * componentRemount.jsx and asyncDelay.js is intentional: each
 * independent mechanism should simulate exactly one Playwright
 * actionability reason, not blur several together.
 */
import { useEffect, useState } from 'react'

export const PointerEventsOverlayMode = {
  OFF: 'off',
  PERMANENT: 'permanent',
  TRANSIENT: 'transient',
}

/**
 * Renders a full-viewport, transparent, pointer-event-capturing div
 * alongside its children when active. children remain completely
 * unmodified (same selector, same visibility, same DOM position) —
 * only a sibling element is added on top, and — in TRANSIENT mode —
 * later removed outright.
 *
 * Usage:
 *   <PointerEventsOverlay mode={pointerEventsOverlayMode} delayMs={pointerEventsOverlayMs}>
 *     <button data-testid="btn-login">Log in</button>
 *   </PointerEventsOverlay>
 */
export function PointerEventsOverlay({ mode = PointerEventsOverlayMode.OFF, delayMs = 1000, children }) {
  const [showOverlay, setShowOverlay] = useState(mode !== PointerEventsOverlayMode.OFF)

  useEffect(() => {
    if (mode === PointerEventsOverlayMode.TRANSIENT) {
      setShowOverlay(true)
      const id = setTimeout(() => setShowOverlay(false), delayMs)
      return () => clearTimeout(id)
    }
    setShowOverlay(mode === PointerEventsOverlayMode.PERMANENT)
  }, [mode, delayMs])

  if (mode === PointerEventsOverlayMode.OFF || !showOverlay) {
    return children
  }

  const transientStyle =
    mode === PointerEventsOverlayMode.TRANSIENT
      ? { transitionProperty: 'opacity', transitionDuration: `${delayMs}ms` }
      : {}

  return (
    <>
      {children}
      <div
        data-testid="chaos-pointer-events-overlay"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          background: 'transparent',
          zIndex: 9999,
          ...transientStyle,
        }}
      />
    </>
  )
}
