/**
 * shadowDom.js
 *
 * Realism: 5/10 — real, but narrower in applicability than the other
 * 3 mechanisms. Matters most for Web Components / LWC-style platforms
 * (Salesforce being the canonical enterprise example).
 *
 * KEY DECISION (see LEARNINGS.md "Sprint 1 — Shadow DOM decoupled"):
 * This is NOT part of CHAOS_LEVELS. It's a different AXIS of difficulty
 * (structural DOM access) rather than "more chaos" on the same ladder.
 * It's controlled by its own independent flag, combinable with any level
 * — e.g. HIGH + shadow_dom_enabled tests "refactor + timing + structural
 * access" as an explicit, named combination.
 *
 * Standard Playwright locators (page.locator(selector)) DO NOT pierce
 * shadow boundaries unless using Playwright's built-in piercing behavior.
 * This component creates a REAL shadow root via the native Web Component
 * API so the healer has to deal with an actual shadow boundary, not a
 * simulated one.
 */
import { useEffect, useRef } from 'react'

/**
 * Wraps children in a real Shadow DOM boundary using a custom element.
 * React doesn't render INTO shadow roots natively, so this uses a small
 * imperative bridge: create a custom element, attach a shadow root to it,
 * and move the already-rendered children's DOM node inside it after mount.
 *
 * Usage:
 *   <ShadowDomWrapper active={settings.shadowDomEnabled}>
 *     <button data-testid="btn-login">Login</button>
 *   </ShadowDomWrapper>
 */
export function ShadowDomWrapper({ active, children }) {
  const hostRef = useRef(null)
  const lightDomRef = useRef(null)

  useEffect(() => {
    if (!active || !hostRef.current || !lightDomRef.current) return

    const host = hostRef.current
    // Avoid attaching twice if this effect re-runs (e.g. React strict mode)
    const shadowRoot = host.shadowRoot || host.attachShadow({ mode: 'open' })

    // Move the actual rendered content into the shadow root.
    // This makes it genuinely unreachable via a plain CSS selector from
    // the main document — exactly the failure mode this mechanism tests.
    if (lightDomRef.current.parentNode === host) {
      shadowRoot.appendChild(lightDomRef.current)
    }
  }, [active])

  if (!active) {
    return children
  }

  return (
    <phoenix-chaos-shadow-host ref={hostRef}>
      <div ref={lightDomRef}>{children}</div>
    </phoenix-chaos-shadow-host>
  )
}
