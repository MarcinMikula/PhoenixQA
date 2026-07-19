"""
test_context_collector.py

Unit tests for ContextCollector as a thin router — confirms it
classifies via parse_playwright_call_log() and delegates to the correct
collector per FailureCategory, raising NotImplementedError loudly (not
silently) for categories with no collector at all (REFERENCE). See
LEARNINGS.md "Sprint 6B (implementation)" for the router-split decision
and the ActionabilityCollector addition.

Collector-specific logic lives in its own test file per collector:
  - tests/unit/test_locator_resolution_collector.py (tokenization, etc.)
  - tests/unit/test_actionability_collector.py (RECEIVES_EVENTS context
    gathering, NotImplementedError for the other four reasons)
This file only tests the routing decision itself.
"""
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from phoenix.collector.context_collector import ContextCollector


@pytest.mark.unit
class TestContextCollectorRouting:
    def test_locator_resolution_delegates_to_locator_resolution_collector(self):
        page = MagicMock()
        collector = ContextCollector(page)
        collector._locator_resolution_collector = MagicMock()
        collector._locator_resolution_collector.collect.return_value = "sentinel-locator-context"

        error = PlaywrightTimeout(
            "Locator.click: Timeout 10000ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='btn-login']\")\n"
        )
        result = collector.collect("[data-testid='btn-login']", error, "click")

        assert result == "sentinel-locator-context"
        collector._locator_resolution_collector.collect.assert_called_once()

    def test_actionability_delegates_to_actionability_collector(self):
        page = MagicMock()
        collector = ContextCollector(page)
        collector._actionability_collector = MagicMock()
        collector._actionability_collector.collect.return_value = "sentinel-actionability-context"

        # Real capture shape from Sprint 6B's overlay diagnostic —
        # locator resolved, receives_events reason.
        error = PlaywrightTimeout(
            "Locator.click: Timeout 200ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"#target\")\n"
            "    - locator resolved to <button id=\"target\">Click me</button>\n"
            "  - attempting click action\n"
            "    - element is visible, enabled and stable\n"
            "    - <div id=\"overlay\"></div> intercepts pointer events\n"
        )
        result = collector.collect("#target", error, "click")

        assert result == "sentinel-actionability-context"
        collector._actionability_collector.collect.assert_called_once()

    def test_reference_raises_not_implemented_loudly(self):
        page = MagicMock()
        collector = ContextCollector(page)

        error = PlaywrightTimeout(
            "Locator.click: Timeout 10000ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='btn-login']\")\n"
            "  - locator resolved to <button>Log in</button>\n"
            "  - element is not attached to the DOM"
        )
        with pytest.raises(NotImplementedError, match="reference"):
            collector.collect("[data-testid='btn-login']", error, "click")