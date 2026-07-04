"""
test_base_page.py

Regression tests for the bug found via the Sprint 6A live verification
attempt (see LEARNINGS.md): BasePage.click()/fill() must catch
HealingRejectedError / HealingLimitExceededError / HealingFailedError and
re-raise the ORIGINAL Playwright exception that triggered healing, per
healer.py's documented contract — not let the Healer's internal exception
propagate to pytest in its place.

All Healer interaction is mocked via _get_healer() — these tests verify
BasePage's exception-handling wiring, not the Healer's own decision logic
(that's covered by tests/unit/test_healer.py).
"""
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from pages.base_page import BasePage
from phoenix.healing.healer import (
    HealingFailedError,
    HealingLimitExceededError,
    HealingRejectedError,
)


def _make_page_with_click_failure():
    """
    A mock Playwright Page whose locator().click() raises a TimeoutError
    on the FIRST call (the original, broken selector) — the same shape
    BasePage.click() is written to catch.
    """
    page = MagicMock()
    failing_locator = MagicMock()
    failing_locator.click.side_effect = PlaywrightTimeout("Locator.click: Timeout 10000ms exceeded.")
    page.locator.return_value = failing_locator
    return page, failing_locator


def _make_base_page_with_mocked_healer(page):
    base_page = BasePage(page, settings=MagicMock(default_timeout=10000))
    base_page._healer = MagicMock()  # bypasses _get_healer()'s real construction
    return base_page


@pytest.mark.unit
class TestBasePageClickHealingExceptionHandling:
    def test_healing_rejected_reraises_original_timeout_not_healing_exception(self):
        page, failing_locator = _make_page_with_click_failure()
        base_page = _make_base_page_with_mocked_healer(page)
        base_page._healer.attempt_heal.side_effect = HealingRejectedError(
            "Autonomous policy rejected proposed fix '' ... confidence 0.00 below policy threshold 0.75"
        )

        with pytest.raises(PlaywrightTimeout, match="Timeout 10000ms exceeded"):
            base_page.click("[data-testid='btn-login']", healing=True)

        # Confirms the SAME original exception object is what pytest
        # would see — not just "some TimeoutError", but the one actually
        # raised by the failing click() call.
        failing_locator.click.assert_called_once()

    def test_healing_limit_exceeded_reraises_original_timeout(self):
        page, _ = _make_page_with_click_failure()
        base_page = _make_base_page_with_mocked_healer(page)
        base_page._healer.attempt_heal.side_effect = HealingLimitExceededError(
            "Cannot attempt healing: max_attempts_total (5) reached"
        )

        with pytest.raises(PlaywrightTimeout):
            base_page.click("[data-testid='btn-login']", healing=True)

    def test_healing_failed_reraises_original_timeout(self):
        page, _ = _make_page_with_click_failure()
        base_page = _make_base_page_with_mocked_healer(page)
        base_page._healer.attempt_heal.side_effect = HealingFailedError(
            "Healing pipeline raised an exception: Ollama connection refused"
        )

        with pytest.raises(PlaywrightTimeout):
            base_page.click("[data-testid='btn-login']", healing=True)

    def test_successful_heal_retries_with_healed_selector_no_exception(self):
        # The counterpart to the three tests above — confirms the fix
        # didn't accidentally break the happy path. A successful heal
        # must still retry the action with the new selector and raise
        # nothing.
        page, failing_locator = _make_page_with_click_failure()
        healed_locator = MagicMock()  # click() succeeds, no side_effect
        page.locator.side_effect = [failing_locator, healed_locator]

        base_page = _make_base_page_with_mocked_healer(page)
        base_page._healer.attempt_heal.return_value = "[data-testid='btn-login-4t64']"

        base_page.click("[data-testid='btn-login']", healing=True)

        healed_locator.click.assert_called_once_with(timeout=10000)

    def test_healing_disabled_reraises_immediately_without_calling_healer(self):
        page, _ = _make_page_with_click_failure()
        base_page = _make_base_page_with_mocked_healer(page)

        with pytest.raises(PlaywrightTimeout):
            base_page.click("[data-testid='btn-login']", healing=False)

        base_page._healer.attempt_heal.assert_not_called()


@pytest.mark.unit
class TestBasePageFillHealingExceptionHandling:
    def _make_page_with_fill_failure(self):
        page = MagicMock()
        failing_locator = MagicMock()
        failing_locator.fill.side_effect = PlaywrightTimeout("Locator.fill: Timeout 30000ms exceeded.")
        page.locator.return_value = failing_locator
        return page, failing_locator

    def test_healing_rejected_reraises_original_timeout_not_healing_exception(self):
        page, failing_locator = self._make_page_with_fill_failure()
        base_page = _make_base_page_with_mocked_healer(page)
        base_page._healer.attempt_heal.side_effect = HealingRejectedError("rejected")

        with pytest.raises(PlaywrightTimeout, match="Timeout 30000ms exceeded"):
            base_page.fill("[data-testid='username']", "admin", healing=True)

        failing_locator.fill.assert_called_once_with("admin")