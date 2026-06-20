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
    console.warn(`[chaosConfig] Unknown level "${level}", falling back to MEDIUM`)
    return CHAOS_LEVELS.MEDIUM.mechanisms
  }
  return entry.mechanisms
}

/**
 * Reads current config from Vite env vars (set via .env at chaos_app root,
 * mirrors the PhoenixQA root .env so both sides agree on the same run).
 */
export function getChaosConfigFromEnv() {
  const level = import.meta.env.VITE_CHAOS_LEVEL || 'MEDIUM'
  const shadowDomEnabled = import.meta.env.VITE_SHADOW_DOM_ENABLED === 'true'

  return {
    level: level.toUpperCase(),
    mechanisms: getMechanismsForLevel(level),
    shadowDomEnabled,
  }
}
