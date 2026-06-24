"""
context_collector.py

Gathers everything the LLM Analyzer (Sprint 3) needs to diagnose a failure.
Sprint 2 scope: only FailureType.SELECTOR_NOT_FOUND has a real
implementation. See LEARNINGS.md "Gap #4" for why the other FailureType
values raise NotImplementedError here rather than being half-built.

ARCHITECTURE (see LEARNINGS.md "Refinement: scoring must start from the
selector name, not DOM position" for the full reasoning trail):

  1. Tokenize the broken selector — extract meaningful name fragments,
     filter out random rotation suffixes (noise from our own
     selectorRotation.js, not signal).
  2. Score every candidate element in the DOM against those tokens,
     weighted by HOW INTENTIONAL each attribute is as a test hook
     (data-testid >> textContent).
  3. Keep ties — don't arbitrarily break them. Ambiguity is real
     information for the LLM, not a problem to paper over.
  4. From the best-scoring candidate(s), walk UP to the nearest
     form/section/role landmark — NOT from an arbitrary DOM position.
  5. Shadow DOM is scored in its own pass (document.querySelectorAll never
     sees into shadow roots, so it can't be folded into step 2).
  6. Apply a dual limit (max depth OR max chars, whichever hits first)
     before handing anything to the LLM.

KNOWN FRAGILITY (tracked, not fixed yet — see LEARNINGS.md, Sprint 3
TODO): re-finding an element by outerHTML string match collides when two
elements are structurally identical (e.g. TicketList's three rows). Sprint
3 replaces this with a retained ElementHandle from the same evaluate()
call instead of re-querying the DOM a second time.
"""
import re

from playwright.sync_api import Page

from phoenix.ai.base_provider import HealingContext
from phoenix.collector.failure_classifier import FailureType, classify_playwright_error

# Sprint 2 tuning constants — not derived from real data yet (see
# LEARNINGS.md Gap #7, cost accounting). Revisit once Sprint 3/4 give us
# actual token-cost-vs-quality numbers to calibrate against.
MAX_SNAPSHOT_CHARS = 4000
MAX_LANDMARK_DEPTH = 4

# Weighted by how INTENTIONAL each source is as a test hook, not flat +1
# per match. data-testid is deliberately placed by a developer for tests;
# textContent matching is incidental. See LEARNINGS.md for the worked
# example (data-testid match scores 5x a textContent-only match).
SCORE_WEIGHTS = {
    "data-testid": 5,
    "aria-label": 4,
    "name": 4,
    "placeholder": 3,
    "id": 2,
    "textContent": 1,
}

# Random rotation suffixes from selectorRotation.js are 4-char base36
# strings (see chaos_app/src/chaos/selectorRotation.js randomSuffix()).
# Matching on length alone is too aggressive — real words like "form" or
# "name" are also 4 letters and would get wrongly stripped. A genuine
# rotation suffix is base36 (letters AND digits), so it must contain at
# least one digit to be treated as noise rather than signal.
_ROTATION_SUFFIX_RE = re.compile(r"-(?=[a-z0-9]{4}$)(?=[a-z]*[0-9])[a-z0-9]{4}$")


def tokenize_selector(selector: str) -> list:
    """
    Extracts meaningful name fragments from a CSS selector string.

    Examples:
        "[data-testid='username-ab12']" -> ["username"]
        "#btn-login"                     -> ["btn", "login"]
        "[data-testid='save-customer']"  -> ["save", "customer"]

    Deliberately simple for Sprint 2 — handles attribute selectors
    ([data-testid='...']), id selectors (#...), and class selectors
    (....). Anything more exotic (XPath, :nth-child, etc.) is out of
    scope; Chaos App only ever generates the selector shapes above.
    """
    match = re.search(r"""['"]([^'"]+)['"]""", selector)  # [data-testid='...']
    if match:
        raw = match.group(1)
    elif selector.startswith("#") or selector.startswith("."):
        raw = selector[1:]
    else:
        raw = selector

    # Strip a trailing rotation suffix if present — it's noise, not signal.
    raw = _ROTATION_SUFFIX_RE.sub("", raw)

    tokens = [t for t in re.split(r"[-_\s]+", raw) if t]
    return tokens


_SCORE_CANDIDATES_JS = """
    ([tokens, weights]) => {
        const results = [];
        const elements = document.querySelectorAll(
            'input, button, select, textarea, label, a, [role]'
        );
        elements.forEach(el => {
            let score = 0;
            const sources = {
                'data-testid': el.getAttribute('data-testid') || '',
                'aria-label': el.getAttribute('aria-label') || '',
                'name': el.getAttribute('name') || '',
                'placeholder': el.getAttribute('placeholder') || '',
                'id': el.id || '',
                'textContent': el.textContent || '',
            };
            for (const token of tokens) {
                const lowerToken = token.toLowerCase();
                for (const [source, value] of Object.entries(sources)) {
                    if (value.toLowerCase().includes(lowerToken)) {
                        score += weights[source];
                    }
                }
            }
            if (score > 0) {
                results.push({
                    score,
                    tag: el.tagName.toLowerCase(),
                    outerHTML: el.outerHTML,
                });
            }
        });
        results.sort((a, b) => b.score - a.score);
        return results;
    }
"""

_FIND_LANDMARK_JS = """
    ([candidateHTML, maxDepth]) => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            if (el.outerHTML === candidateHTML) {
                let node = el;
                for (let depth = 0; depth < maxDepth; depth++) {
                    if (!node.parentElement) break;
                    node = node.parentElement;
                    const tag = node.tagName.toLowerCase();
                    if (tag === 'form' || tag === 'section' || node.hasAttribute('role')) {
                        return node.outerHTML;
                    }
                }
                return node.outerHTML;
            }
        }
        return null;
    }
"""

_SCORE_SHADOW_CANDIDATES_JS = """
    ([tokens, weights]) => {
        const results = [];
        const hosts = document.querySelectorAll('*');
        hosts.forEach(host => {
            if (!host.shadowRoot) return;
            const elements = host.shadowRoot.querySelectorAll(
                'input, button, select, textarea, label, a, [role]'
            );
            elements.forEach(el => {
                let score = 0;
                const sources = {
                    'data-testid': el.getAttribute('data-testid') || '',
                    'aria-label': el.getAttribute('aria-label') || '',
                    'name': el.getAttribute('name') || '',
                    'placeholder': el.getAttribute('placeholder') || '',
                    'id': el.id || '',
                    'textContent': el.textContent || '',
                };
                for (const token of tokens) {
                    const lowerToken = token.toLowerCase();
                    for (const [source, value] of Object.entries(sources)) {
                        if (value.toLowerCase().includes(lowerToken)) {
                            score += weights[source];
                        }
                    }
                }
                if (score > 0) {
                    results.push({
                        score,
                        tag: el.tagName.toLowerCase(),
                        outerHTML: el.outerHTML,
                        shadowHost: host.tagName.toLowerCase(),
                    });
                }
            });
        });
        results.sort((a, b) => b.score - a.score);
        return results;
    }
"""


class ContextCollector:
    def __init__(self, page: Page):
        self.page = page

    def collect(self, broken_selector: str, error: Exception, original_code: str) -> HealingContext:
        """
        Main entry point — called from Healer (Sprint 4/5) when a
        Playwright action fails. Classifies the failure, then routes to
        the appropriate collection strategy.
        """
        failure_type = classify_playwright_error(error, page=self.page, selector=broken_selector)

        if failure_type == FailureType.SELECTOR_NOT_FOUND:
            return self._collect_selector_context(broken_selector, error, original_code, failure_type)

        # Sprint 6 scope (see LEARNINGS.md "Gap #4" and the Sprint 6 spec
        # for componentRemount.jsx). Explicit and loud, not a silent
        # fallback that would produce misleading context.
        raise NotImplementedError(
            f"ContextCollector has no collection strategy for {failure_type.value} yet. "
            f"Planned for Sprint 6 (Failure type expansion) — see LEARNINGS.md."
        )

    def _collect_selector_context(
        self,
        broken_selector: str,
        error: Exception,
        original_code: str,
        failure_type: FailureType,
    ) -> HealingContext:
        tokens = tokenize_selector(broken_selector)

        # Score light-DOM and shadow-DOM candidates separately — they
        # need different querying strategies (document.querySelectorAll
        # never sees into shadow roots), so this can't be one pass.
        light_candidates = self.page.evaluate(_SCORE_CANDIDATES_JS, [tokens, SCORE_WEIGHTS])
        shadow_candidates = self.page.evaluate(_SCORE_SHADOW_CANDIDATES_JS, [tokens, SCORE_WEIGHTS])

        all_candidates = light_candidates + shadow_candidates
        all_candidates.sort(key=lambda c: c["score"], reverse=True)

        if not all_candidates:
            # No semantic match anywhere. Don't fabricate a landmark —
            # be honest that nothing was found, so the LLM (Sprint 3)
            # reasons from the selector string and error message alone
            # rather than a misleading "context" that wasn't really one.
            dom_snapshot = "<!-- no matching elements found in light DOM or shadow roots -->"
        else:
            top_score = all_candidates[0]["score"]
            top_candidates = [c for c in all_candidates if c["score"] == top_score]

            landmark_snapshots = []
            for candidate in top_candidates:
                landmark_html = self.page.evaluate(
                    _FIND_LANDMARK_JS, [candidate["outerHTML"], MAX_LANDMARK_DEPTH]
                )
                if landmark_html:
                    landmark_snapshots.append(landmark_html)

            dom_snapshot = (
                "\n---\n".join(landmark_snapshots)
                if landmark_snapshots
                else "<!-- landmark lookup failed -->"
            )

        if len(dom_snapshot) > MAX_SNAPSHOT_CHARS:
            dom_snapshot = dom_snapshot[:MAX_SNAPSHOT_CHARS] + "\n<!-- truncated -->"

        return HealingContext(
            broken_selector=broken_selector,
            error_message=str(error),
            dom_snapshot=dom_snapshot,
            page_url=self.page.url,
            original_code=original_code,
            failure_type=failure_type,
            screenshot_path=None,  # Gap #8 — deliberately undecided, see LEARNINGS.md
        )