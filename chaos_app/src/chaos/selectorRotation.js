/**
 * selectorRotation.js
 *
 * Realism: 9/10 — the classic, most common cause of brittle test failures.
 * A developer renames a class, regenerates a data-testid, or a build tool
 * hashes a class name differently. The element is functionally identical;
 * the locator that used to find it no longer works.
 *
 * How it works here:
 * Each "rotating" element gets a fresh suffix appended to its identifying
 * attributes on every mount. A test written against a fixed selector like
 * [data-testid="username"] will find a DIFFERENT value
 * ([data-testid="username-x7f2"]) on the next render — simulating exactly
 * the kind of churn that breaks real test suites.
 */

/**
 * Generates a short random suffix to simulate a hash/build-id style change.
 * Deliberately short (4 chars) — readable in DOM snapshots during debugging,
 * not trying to look like a real production hash.
 */
function randomSuffix() {
  return Math.random().toString(36).slice(2, 6)
}

/**
 * Given a stable "logical" testid, returns a rotated version.
 * Call this ONCE per component mount (e.g. inside useMemo), not on every
 * render of an already-mounted component — otherwise it rotates on every
 * keystroke, which is not realistic and makes the component fight React.
 *
 * @param {string} logicalName - e.g. "username", "btn-login"
 * @param {boolean} active - whether selector_rotation mechanism is enabled
 * @returns {string} either the original name, or name + rotated suffix
 */
export function rotateSelector(logicalName, active) {
  if (!active) return logicalName
  return `${logicalName}-${randomSuffix()}`
}
