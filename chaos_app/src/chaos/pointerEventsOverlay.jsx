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
 * Deterministic by design (same lesson as Sprint 6A's move away from
 * timer-based component remount toward a mousedown trigger, and Sprint
 * 6B's move away from CSS-easing-based animation toward a monotonic
 * requestAnimationFrame loop): the overlay is present continuously
 * while active, not triggered probabilistically — every click attempt
 * anywhere in the viewport is guaranteed to be intercepted, no timing
 * luck involved. This mirrors the exact HTML shape already proven live
 * in Sprint 6B's diagnostic (see LEARNINGS.md "Sprint 6B (pre-coding)"
 * — the overlaid-element capture that produced the RECEIVES_EVENTS
 * reason in the first place).
 *
 * Deliberately NOT the same failure as NOT_VISIBLE or ENABLED — the
 * target element stays fully visible, enabled, and stable; only
 * pointer events are intercepted. Keeping this mechanism separate from
 * componentRemount.jsx and asyncDelay.js is intentional: each
 * independent mechanism should simulate exactly one Playwright
 * actionability reason, not blur several together.
 */

/**
 * Renders a full-viewport, transparent, pointer-event-capturing div
 * alongside its children when active. children remain completely
 * unmodified (same selector, same visibility, same DOM position) — only
 * a sibling element is added on top.
 *
 * Usage:
 *   <PointerEventsOverlay active={pointerEventsOverlayEnabled}>
 *     <button data-testid="btn-login">Log in</button>
 *   </PointerEventsOverlay>
 */
export function PointerEventsOverlay({ active, children }) {
    if (!active) {
      return children
    }
  
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
          }}
        />
      </>
    )
  }