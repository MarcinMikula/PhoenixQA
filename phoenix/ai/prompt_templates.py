"""
prompt_templates.py

Builds the system + user prompt sent to the LLM for Sprint 3.
Kept as its own module — separate from the HTTP/provider plumbing — so the
prompt itself can be iterated on and tested without touching
ollama_provider.py or anthropic_provider.py.

Sprint 3 scope: only builds a prompt for FailureType.SELECTOR_NOT_FOUND.
Other failure types need different prompts entirely ("propose a wait
strategy" vs "propose a selector") — see LEARNINGS.md Gap #4. Building
those prompts now, before Sprint 6 gives us real DETACHED_FROM_DOM/
NOT_VISIBLE context to design against, would be guessing blind.
"""
from phoenix.ai.base_provider import HealingContext

SYSTEM_PROMPT = """You are a test automation engineer's assistant. A Playwright test failed because a CSS selector could not find its target element. This is a test environment that intentionally rotates element identifiers (like data-testid suffixes) on every page load, to simulate real-world UI churn. The element itself still exists on the page — only its identifying attribute value has changed.

HOW TO FIND THE REPLACEMENT — follow these steps in order:
1. Look at the broken selector's value. It has a "base name" and often a short suffix at the end (e.g. "username-h1fz" has base name "username" and suffix "h1fz").
2. Scan the provided HTML for every data-testid, id, name, aria-label, and placeholder attribute value.
3. Find the one whose BASE NAME matches the broken selector's base name, even though its suffix is different (e.g. broken selector base "username" should match an attribute like data-testid="username-mrt2" found in the HTML — "mrt2" is a NEW, DIFFERENT suffix, and that is expected and correct).
4. Your proposed_selector MUST be built from the ACTUAL attribute value you found in the HTML in step 3 — copy it exactly as it appears in the provided HTML. Do NOT reuse the broken selector's old value. If the broken selector and your proposed selector are identical, you have made an error — the whole point is that the old value no longer exists on the page.
5. If you cannot find any matching base name anywhere in the provided HTML, say so honestly with a low confidence score (below 0.3) rather than guessing or repeating the broken selector.

EXAMPLE:
Broken selector: [data-testid='email-ab12']
HTML contains: <input data-testid="email-q9wz" type="email">
Correct response: {"proposed_selector": "[data-testid='email-q9wz']", "confidence": 0.95, "reasoning": "Found an input with data-testid 'email-q9wz' — same base name 'email' as the broken selector, new rotated suffix.", "alternative_selectors": []}

You MUST respond with ONLY a JSON object, no other text before or after it, in exactly this shape:

{
  "proposed_selector": "a valid CSS selector string, built from an actual attribute value found in the provided HTML",
  "confidence": 0.0 to 1.0,
  "reasoning": "one or two sentences naming the SPECIFIC attribute value you found in the HTML and why it matches",
  "alternative_selectors": ["other plausible selector strings, if any, ordered by likelihood"]
}

Rules:
- confidence should reflect how certain you are this is the SAME element, not just any plausible one
- prefer data-testid or aria-label based selectors over positional ones (nth-child, etc.) when available in the context
- do not include explanation text outside the JSON object — your entire response must be parseable as JSON
- keep "reasoning" to one short sentence — brevity matters more than detail, a long reasoning field risks an incomplete response
"""


def build_user_prompt(context: HealingContext) -> str:
    """
    Renders a HealingContext into the user-facing prompt text.
    Sprint 3: assumes context.failure_type == SELECTOR_NOT_FOUND — this
    function is only ever called from that path (see provider implementations).
    """
    return f"""A test action failed with this error:
{context.error_message}

The broken selector was:
{context.broken_selector}

The original test code being executed was:
{context.original_code}

The page URL at the time of failure was:
{context.page_url}

Here is the relevant DOM context collected near where the element should be:
```html
{context.dom_snapshot}
```

Propose the replacement selector as a JSON object, following the format and rules in your instructions."""
