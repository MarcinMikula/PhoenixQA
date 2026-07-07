"""
THROWAWAY DIAGNOSTIC — not part of the permanent suite. Completes the
actionability-reason picture: does click() report a distinct Reason for
"stable" (animating element) and "receives events" (covered by an
overlay), the same way fill() did for enabled/visible/editable? Self-
contained via page.set_content() — no running Chaos App needed. Delete
after capturing the result.
"""
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout


def _capture(page, html, label, timeout=200):
    page.set_content(html)
    try:
        page.locator("#target").click(timeout=timeout)
    except PlaywrightTimeout as e:
        print(f"\n{'=' * 70}\nCLICK() ON {label} — paste this back to Claude\n{'=' * 70}")
        print(repr(str(e)))
        print("=" * 70)
        raise


def test_click_on_unstable_element(page):
    # Continuous CSS animation — bounding box never settles between
    # two consecutive frames, so Playwright's stability check never
    # succeeds. Longer timeout + bigger displacement than the first
    # attempt, which was too short to let Playwright report a reason.
    html = """
    <style>
      @keyframes shake { 0% { transform: translateX(0px); }
                         50% { transform: translateX(60px); }
                         100% { transform: translateX(0px); } }
      #target { animation: shake 0.3s linear infinite; }
    </style>
    <button id="target">Click me</button>
    """
    _capture(page, html, "UNSTABLE (animating)", timeout=600)


def test_click_on_overlaid_element(page):
    # A full-viewport, invisible-but-present div sits on top of the
    # button at the same screen coordinates — pointer events land on
    # the overlay, never reach the button underneath.
    html = """
    <button id="target">Click me</button>
    <div id="overlay" style="position:fixed;top:0;left:0;
         width:100vw;height:100vh;background:transparent;z-index:9999;">
    </div>
    """
    _capture(page, html, "OVERLAID (covered)")