/**
 * chaosConfig.js
 *
 * Single source of truth for which chaos mechanisms are active.
 *
 * KEY DECISION (see PhoenixQA LEARNINGS.md "Sprint 1 pivot"):
 * A level represents a RESEARCH SCENARIO, not a quantity of chaos.
 * It's a dict (level -> mechanism list), not a count. This means adding
 * a 5th mechanism later (e.g. "a11y_noise") never breaks this structure —
 * we just add it to whichever level's list makes sense.
 *
 * Shadow DOM is deliberately NOT part of this ladder. It's a different
 * AXIS of difficulty (structural DOM access) rather than "more chaos."
 * It's controlled by its own independent flag below, combinable with
 * any level — e.g. HIGH + shadow_dom is a valid, explicit combination.
 *
 * Component Remount (Sprint 6A) is the SAME kind of independent flag,
 * for the same reason: it isn't "more chaos" on the selector-rename/
 * DOM-structure/timing axis the levels already cover — it's a different
 * failure family entirely (DETACHED_FROM_DOM). Combinable with any
 * level, same as shadow DOM.
 *
 * Pointer Events Overlay (Sprint 6B) is a THIRD independent flag, same
 * pattern again — simulates ActionabilityReason.RECEIVES_EVENTS
 * (Playwright's FailureCategory.ACTIONABILITY family), a different axis
 * entirely from selector rotation, DOM mutation, timing, or reference
 * loss. See LEARNINGS.md "Sprint 6B (implementation) —
 * ActionabilityCollector".
 *
 * TWO CLASSES OF MECHANISM (clarified via Sprint 6A live-verification
 * discussion, see LEARNINGS.md "Sprint 6A — mechanism override"):
 *   - CORE mechanisms (this file's CHAOS_LEVELS ladder): selector_rotation,
 *     dom_mutation, async_delay. These cumulatively define the official
 *     LOW/MEDIUM/HIGH benchmark scenarios (Sprint 7/8) — the ladder
 *     itself is NOT changed by anything below.
 *   - INDEPENDENT mechanisms: shadow_dom, component_remount,
 *     pointer_events_overlay (and future additions). Orthogonal axes,
 *     toggled by their own flags, layered on top of whichever level is
 *     active.
 *
 * MECHANISM OVERRIDES (Sprint 6A addition — see LEARNINGS.md for the
 * full discussion, including why a "NONE" level was considered and
 * rejected): a "no chaos" level and a "developer isolation tool" are two
 * different needs that happened to look similar at first. A level
 * conflates "which mechanisms are active" with "the official named
 * research scenario a level represents" — collapsing them loses the
 * ability to ask "LOW's mechanisms, minus rotation, plus
 * component_remount" without inventing a new named level for every such
 * combination. Overrides solve this generally: they let ANY core
 * mechanism be forced on/off independently of which level is configured,
 * for development/verification purposes, WITHOUT changing what LOW/
 * MEDIUM/HIGH mean for the benchmark. The level ladder itself stays the
 * single source of truth for the three official scenarios; overrides
 * are a development-time lens on top of it, never persisted into
 * CHAOS_LEVELS itself.
 */

export const CHAOS_LEVELS = {
  LOW: {
    mechanisms: ['selector_rotation'],
    researchQuestion: 'Does the test survive a selector rename?',
  },
  MEDIUM: {
    mechanisms: ['selector_rotation', 'dom_mutation'],
    researchQuestion: 'Does the test survive a UI refactor?',
  },
  HIGH: {
    mechanisms: ['selector_rotation', 'dom_mutation', 'async_delay'],
    researchQuestion: 'Does the test survive a refactor + timing issues?',
  },
}

// Every mechanism an override is allowed to touch. Deliberately an
// explicit allow-list rather than "any string" — a typo'd override key
// (e.g. VITE_OVERRIDE_SELCTOR_ROTATION) should be silently ignored, not
// silently accepted and then just never matched by anything downstream.
const OVERRIDABLE_MECHANISMS = [
  'selector_rotation',
  'dom_mutation',
  'async_delay',
]

/**
 * Returns the list of active mechanism names for a given level.
 * This is the single function both the app AND the future benchmark
 * runner (Sprint 7) call — no duplicated mapping logic anywhere else.
 *
 * @param {string} level - "LOW" | "MEDIUM" | "HIGH"
 * @returns {string[]} active mechanism names for that level
 */
export function getMechanismsForLevel(level) {
  const normalized = (level || 'MEDIUM').toUpperCase()
  const entry = CHAOS_LEVELS[normalized]

  if (!entry) {
    console.warn(
      `[chaosConfig] Unknown level "${level}", falling back to MEDIUM`
    )
    return CHAOS_LEVELS.MEDIUM.mechanisms
  }

  return entry.mechanisms
}

/**
 * Applies development-time overrides on top of a level's base mechanism
 * list. `overrides` is a plain object like `{ selector_rotation: false }`
 * — only keys actually present override anything; an absent key means
 * "use whatever the level already says," so a partial override (e.g.
 * just turning selector_rotation off) never has to also restate every
 * other mechanism the level would otherwise include.
 *
 * @param {string[]} baseMechanisms - mechanisms from getMechanismsForLevel()
 * @param {Object.<string, boolean>} overrides
 * @returns {string[]} final active mechanism list
 */
export function applyMechanismOverrides(baseMechanisms, overrides) {
  const active = new Set(baseMechanisms)

  for (const [mechanism, enabled] of Object.entries(overrides)) {
    if (enabled) {
      active.add(mechanism)
    } else {
      active.delete(mechanism)
    }
  }

  return Array.from(active)
}

/**
 * Reads per-mechanism override env vars, if present. Each is OPTIONAL —
 * an unset var means "don't override this mechanism, use the level's
 * default" — so existing runs (Sprint 1-6) that never set any of these
 * are completely unaffected. Only meant for development/verification use
 * (e.g. isolating DETACHED_FROM_DOM by forcing selector_rotation off
 * while at LOW) — never intended for the official Sprint 7/8 benchmark
 * runs, which should always use plain CHAOS_LEVEL with no overrides.
 */
function readMechanismOverridesFromEnv() {
  const envKeyFor = {
    selector_rotation: 'VITE_OVERRIDE_SELECTOR_ROTATION',
    dom_mutation: 'VITE_OVERRIDE_DOM_MUTATION',
    async_delay: 'VITE_OVERRIDE_ASYNC_DELAY',
  }

  const overrides = {}

  for (const mechanism of OVERRIDABLE_MECHANISMS) {
    const raw = import.meta.env[envKeyFor[mechanism]]

    if (raw !== undefined) {
      overrides[mechanism] = raw === 'true'
    }
  }

  return overrides
}

/**
 * Reads current config from Vite env vars (set via .env at chaos_app root,
 * mirrors the PhoenixQA root .env so both sides agree on the same run).
 */
export function getChaosConfigFromEnv() {
  const level = import.meta.env.VITE_CHAOS_LEVEL || 'MEDIUM'

  const shadowDomEnabled =
    import.meta.env.VITE_SHADOW_DOM_ENABLED === 'true'

  // Sprint 6A — independent flag, same pattern as shadowDomEnabled above.
  // Defaults to false so existing runs (Sprint 1-5) are unaffected unless
  // explicitly opted in.
  const componentRemountEnabled =
    import.meta.env.VITE_COMPONENT_REMOUNT_ENABLED === 'true'

  const componentRemountMinMs = import.meta.env.VITE_COMPONENT_REMOUNT_MIN_MS
    ? parseInt(import.meta.env.VITE_COMPONENT_REMOUNT_MIN_MS, 10)
    : undefined

  const componentRemountMaxMs = import.meta.env.VITE_COMPONENT_REMOUNT_MAX_MS
    ? parseInt(import.meta.env.VITE_COMPONENT_REMOUNT_MAX_MS, 10)
    : undefined

  // Optional — 'timeout' (default, realistic/probabilistic) or
  // 'mousedown' (deterministic verification trigger).
  const componentRemountTrigger =
    import.meta.env.VITE_COMPONENT_REMOUNT_TRIGGER || undefined

  // Sprint 6B — independent flag, same pattern again. Defaults to false
  // so existing runs (Sprint 1-6A) are unaffected unless explicitly
  // opted in.
  const pointerEventsOverlayEnabled =
    import.meta.env.VITE_POINTER_EVENTS_OVERLAY_ENABLED === 'true'

  const baseMechanisms = getMechanismsForLevel(level)
  const overrides = readMechanismOverridesFromEnv()
  const mechanisms = applyMechanismOverrides(baseMechanisms, overrides)

  return {
    level: level.toUpperCase(),
    mechanisms,
    shadowDomEnabled,
    componentRemountEnabled,
    componentRemountMinMs,
    componentRemountMaxMs,
    componentRemountTrigger,
    pointerEventsOverlayEnabled,
  }
}