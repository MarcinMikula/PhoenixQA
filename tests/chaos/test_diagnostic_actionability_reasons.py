"""
THROWAWAY DIAGNOSTIC — not part of the permanent suite. Retest of the
"stable" actionability reason with a deterministic, monotonic
requestAnimationFrame loop instead of CSS keyframes — the CSS version's
default easing has near-zero-velocity dwell points near each keyframe,
which let click() succeed by chance instead of reliably failing. Delete
this file after capturing the result.
"""
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout


def test_click_on_unstable_element(page):
    html = """
    <button id="target">Click me</button>
    <script>
      let x = 0;
      function loop() {
        x = (x + 5) % 100;
        document.getElementById('target').style.transform = `translateX(${x}px)`;
        requestAnimationFrame(loop);
      }
      requestAnimationFrame(loop);
    </script>
    """
    page.set_content(html)
    try:
        page.locator("#target").click(timeout=300)
    except PlaywrightTimeout as e:
        print(f"\n{'=' * 70}\nCLICK() ON UNSTABLE (rAF, monotonic) — paste this back to Claude\n{'=' * 70}")
        print(repr(str(e)))
        print("=" * 70)
        raise