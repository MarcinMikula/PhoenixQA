"""
test_context_collector.py

Unit tests for ContextCollector as a thin router — confirms it
classifies via parse_playwright_call_log() and delegates to
LocatorResolutionCollector for FailureCategory.LOCATOR_RESOLUTION,
raising NotImplementedError loudly (not silently) for ACTIONABILITY and
the dormant REFERENCE category. See LEARNINGS.md "Sprint 6B
(implementation)" for the router-split decision.

Collector-specific logic (tokenization, DOM scoring, landmark walking)
now lives in tests/unit/test_locator_resolution_collector.py, mirroring
the phoenix/collector/collectors/ split — this file only tests the
routing decision, not what any individual collector does.
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
        collector._locator_resolution_collector.collect.return_value = "sentinel-context"

        error = PlaywrightTimeout(
            "Locator.click: Timeout 10000ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"[data-testid='btn-login']\")\n"
        )
        result = collector.collect("[data-testid='btn-login']", error, "click")

        assert result == "sentinel-context"
        collector._locator_resolution_collector.collect.assert_called_once()

    def test_actionability_raises_not_implemented_loudly(self):
        page = MagicMock()
        collector = ContextCollector(page)

        # Real capture shape from Sprint 6B's disabled-input diagnostic —
        # locator resolved, action could not proceed.
        error = PlaywrightTimeout(
            "Locator.fill: Timeout 100ms exceeded.\n"
            "Call log:\n"
            "  - waiting for locator(\"#target\")\n"
            "    - locator resolved to <input disabled id=\"target\"/>\n"
            "    - fill(\"x\")\n"
            "  - attempting fill action\n"
            "    - element is not enabled\n"
        )
        with pytest.raises(NotImplementedError, match="actionability"):
            collector.collect("#target", error, "fill")

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