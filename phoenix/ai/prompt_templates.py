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

SYSTEM_PROMPT = """You are a test automation engineer's assistant. A Playwright test failed because a CSS selector could not find its target element. The page's DOM structure has NOT changed in a way that breaks the underlying feature — only the selector attributes (like data-testid) may have changed, because this is a test environment that intentionally rotates them to simulate real-world UI churn.

Your job: look at the broken selector and the DOM context provided, and propose the single most likely replacement selector that points to the SAME logical element (same role, same position, same intent) — not a element that merely exists somewhere on the page.

You MUST respond with ONLY a JSON object, no other text before or after it, in exactly this shape:

{
  "proposed_selector": "a valid CSS selector string",
  "confidence": 0.0 to 1.0,
  "reasoning": "one or two sentences explaining why this element is the right match",
  "alternative_selectors": ["other plausible selector strings, if any, ordered by likelihood"]
}

Rules:
- confidence should reflect how certain you are this is the SAME element, not just any plausible one
- if the DOM context doesn't contain enough information to be confident, say so honestly with a low confidence score rather than fabricating certainty
- prefer data-testid or aria-label based selectors over positional ones (nth-child, etc.) when available in the context
- do not include explanation text outside the JSON object — your entire response must be parseable as JSON
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
