/**
 * disabledState.js
 *
 * Independent chaos mechanism (same pattern as shadow_dom,
 * component_remount, pointer_events_overlay, visibility_delay — not
 * part of CHAOS_LEVELS), simulating ActionabilityReason.ENABLED: the
 * target element resolves, is visible and stable, but Playwright's
 * "enabled" actionability check fails because the `disabled` attribute
 * is set. Common real-world causes: a "Submit" button disabled until
 * client-side validation passes, disabled while an async save is in
 * flight, disabled until a required checkbox is ticked.
 *
 * Hook, not a wrapper component — mirrors asyncDelay.js's
 * useChaosDelay() shape (a boolean the caller applies directly to
 * `disabled={...}`), not visibilityDelay.jsx's/pointerEventsOverlay.jsx's
 * wrapper-component shape. A disabled state is a plain boolean prop on
 * the SAME element, not an extra DOM node layered on top the way a
 * hidden-input CSS toggle or a blocking overlay div are — a wrapper
 * would add indirection this mechanism doesn't need.
 *
 * TWO MODES, same PERMANENT/TRANSIENT split as visibilityDelay.jsx and
 * pointerEventsOverlay.jsx before it — built directly into this file
 * from the start (Sprint 8) rather than PERMANENT-only-then-widened,
 * now that the pattern is established:
 *   - PERMANENT: the button never becomes enabled. Ground truth:
 *     no_safe_recovery.
 *   - TRANSIENT: the button becomes enabled after delayMs. Ground
 *     truth: wait_and_retry.
 *
 * Evidence model deliberately mirrors VISIBLE, not RECEIVES_EVENTS —
 * per direct discussion before writing any code. "Disabled → enabled"
 * is a STATE CHANGE observed over time (the same shape as
 * "hidden → visible"), not a declared CSS capability check the way
 * RECEIVES_EVENTS' animation/transition evidence is. No
 * transitionProperty/animationName trick is needed or added here —
 * ActionabilityCollector's ENABLED branch (not yet built) is expected
 * to take two DOM snapshots and compare the `disabled` attribute
 * across them, the same shape as VISIBLE's target_state_changed_during_observation,
 * not RECEIVES_EVENTS' blocking_element_computed_style.
 */
import { useEffect, useState } from 'react'

export const DisabledStateMode = {
  OFF: 'off',
  PERMANENT: 'permanent',
  TRANSIENT: 'transient',
}

/**
 * Hook: returns `true` while the target should be disabled.
 *
 * Usage:
 *   const disabled = useDisabledState(disabledStateMode, disabledStateMs)
 *   <button disabled={disabled} data-testid={testIds.submit}>Log in</button>
 *
 * @param {string} mode - 'off' | 'permanent' | 'transient'
 * @param {number} delayMs - TRANSIENT only: ms until the button becomes enabled
 */
export function useDisabledState(mode = DisabledStateMode.OFF, delayMs = 1000) {
  const [disabled, setDisabled] = useState(mode !== DisabledStateMode.OFF)

  useEffect(() => {
    if (mode === DisabledStateMode.TRANSIENT) {
      setDisabled(true)
      const id = setTimeout(() => setDisabled(false), delayMs)
      return () => clearTimeout(id)
    }
    setDisabled(mode === DisabledStateMode.PERMANENT)
  }, [mode, delayMs])

  return disabled
}