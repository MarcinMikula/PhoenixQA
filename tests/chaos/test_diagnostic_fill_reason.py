"""
THROWAWAY DIAGNOSTIC — not part of the permanent suite. Answers exactly
one question: does fill() report a granular ActionabilityReason (like
click()'s "to be visible") or only the bare "waiting for locator" with
no reason at all? Self-contained via page.set_content() — no running
Chaos App needed. Delete after capturing the result.
"""
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout


def _capture(page, html, label):
    page.set_content(html)
    try:
        page.locator("#target").fill("x", timeout=100)
    except PlaywrightTimeout as e:
        print(f"\n{'=' * 70}\nFILL() ON {label} — paste this back to Claude\n{'=' * 70}")
        print(repr(str(e)))
        print("=" * 70)
        raise


def test_fill_on_disabled_input(page):
    _capture(page, '<input id="target" disabled />', "DISABLED")


def test_fill_on_hidden_input(page):
    _capture(page, '<input id="target" style="display:none" />', "HIDDEN")


def test_fill_on_readonly_input(page):
    _capture(page, '<input id="target" readonly />', "READONLY")