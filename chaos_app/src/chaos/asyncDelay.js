/**
 * asyncDelay.js
 *
 * Realism: 8/10 — lazy loading, animations, network-dependent rendering.
 * The element WILL appear and IS the right element — it just isn't there
 * yet at the moment a naive test tries to interact with it. This tests
 * whether the healer (and the test author's wait strategy) handles
 * timing correctly, not just "wrong selector" cases.
 *
 * Deliberately kept simple: a single async delay before a piece of UI
 * becomes interactive. Real apps have many causes (route transitions,
 * skeleton loaders, debounced search) — we only need one representative
 * case to stress-test timing-related healing.
 */
import { useEffect, useState } from 'react'

/**
 * Returns a random delay in ms, capped to keep test runs from feeling
 * broken rather than realistic. Real loading spinners rarely run past
 * ~2s before a user assumes something is wrong — we mirror that.
 */
function randomDelayMs() {
  return 300 + Math.floor(Math.random() * 1700) // 300ms - 2000ms
}

/**
 * Hook: returns `true` once the simulated delay has elapsed.
 * If `active` is false, returns `true` immediately — zero delay,
 * matching the "stable baseline" behavior used by other mechanisms.
 *
 * @param {boolean} active - whether async_delay mechanism is enabled
 */
export function useChaosDelay(active) {
  const [ready, setReady] = useState(!active)

  useEffect(() => {
    if (!active) {
      setReady(true)
      return
    }
    setReady(false)
    const id = setTimeout(() => setReady(true), randomDelayMs())
    return () => clearTimeout(id)
  }, [active])

  return ready
}
