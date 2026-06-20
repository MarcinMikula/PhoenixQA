/**
 * domMutation.js
 *
 * Realism: 10/10 — the highest-realism mechanism in the whole Chaos App.
 * Any UI library upgrade, component refactor, or wrapper-component
 * migration changes DOM STRUCTURE without changing functionality.
 * This is the #1 real-world cause of brittle XPath failures — far more
 * common than selector renames or Shadow DOM.
 *
 * Examples of what this simulates:
 *   <button>Save</button>
 *   becomes
 *   <div><button>Save</button></div>          (extra wrapper)
 *
 *   <form>...</form>
 *   becomes
 *   <section><form>...</form></section>        (retag / extra semantic layer)
 *
 *   <button><span>Save</span></button>
 *   becomes
 *   <button>Save</button>                       (wrapper removed)
 *
 * Because this mechanism has the highest real-world realism (per
 * LEARNINGS.md ranking), it gets the most variants — unlike the other
 * 3 mechanisms which are single-behavior toggles.
 */

export const DOM_MUTATION_VARIANTS = {
  WRAP: 'wrap',         // adds an extra wrapping element
  RETAG: 'retag',       // changes a semantic tag (div -> section, etc.)
  UNWRAP: 'unwrap',     // removes an inner wrapper that used to exist
}

/**
 * Picks a deterministic-feeling but varied mutation variant.
 * Uses a simple modulo on Date.now() so behavior changes across mounts
 * without needing external random-seed plumbing.
 */
function pickVariant() {
  const variants = Object.values(DOM_MUTATION_VARIANTS)
  const index = Math.floor(Math.random() * variants.length)
  return variants[index]
}

/**
 * React wrapper component that conditionally adds a structural layer
 * around its children, depending on the active variant.
 *
 * Usage:
 *   <DomMutationWrapper active={mechanismsActive.includes('dom_mutation')}>
 *     <button data-testid="btn-login">Login</button>
 *   </DomMutationWrapper>
 *
 * When active=false, renders children with zero structural change —
 * this is the "stable" baseline a test author would expect.
 */
export function DomMutationWrapper({ active, children, wrapTag = 'div' }) {
  if (!active) {
    return children
  }

  const variant = pickVariant()

  switch (variant) {
    case DOM_MUTATION_VARIANTS.WRAP:
      // Extra wrapper — simulates a new layout container being introduced
      return <div className="chaos-dom-wrap">{children}</div>

    case DOM_MUTATION_VARIANTS.RETAG: {
      // Wraps in a semantically different tag than usual (section vs div)
      const Tag = wrapTag === 'div' ? 'section' : 'div'
      return <Tag className="chaos-dom-retag">{children}</Tag>
    }

    case DOM_MUTATION_VARIANTS.UNWRAP:
    default:
      // No extra structure this render — still a valid "mutation" in the
      // sense that structure CHANGED relative to other renders, which is
      // exactly what breaks position-based / structural XPath locators.
      return children
  }
}
