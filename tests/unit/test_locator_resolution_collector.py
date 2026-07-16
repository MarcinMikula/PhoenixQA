"""
test_locator_resolution_collector.py

Unit tests for the pieces of LocatorResolutionCollector that don't need
a live Playwright page — tokenization is pure string logic and should be
verified in isolation before trusting it inside the full collect() flow.

Full collect() behavior (DOM scoring, landmark walking, shadow piercing)
needs a real Page object — that's covered by an integration test against
the actual Chaos App, not here. See tests/integration/ for that.

Moved here unchanged from test_context_collector.py as of the
ContextCollector router split — see LEARNINGS.md "Sprint 6B
(implementation)".
"""
import pytest

from phoenix.collector.collectors.locator_resolution_collector import tokenize_selector


@pytest.mark.unit
class TestTokenizeSelector:
    def test_data_testid_with_rotation_suffix_strips_suffix(self):
        # The exact shape selectorRotation.js produces — this is the
        # primary case the whole function exists for.
        tokens = tokenize_selector("[data-testid='username-ab12']")
        assert tokens == ["username"]

    def test_id_selector_splits_on_hyphen(self):
        tokens = tokenize_selector("#btn-login")
        assert tokens == ["btn", "login"]

    def test_data_testid_multi_word_without_rotation_suffix(self):
        # "customer" is 8 chars, not 4 — must NOT be stripped as a
        # rotation suffix just because it follows a hyphen.
        tokens = tokenize_selector("[data-testid='save-customer']")
        assert tokens == ["save", "customer"]

    def test_class_selector(self):
        tokens = tokenize_selector(".chaos-form")
        assert tokens == ["chaos", "form"]

    def test_does_not_over_strip_short_real_words(self):
        # A 4-char real word that happens to look like a rotation
        # suffix shape (letters+digits) is an edge case worth being
        # aware of — documenting current behavior rather than asserting
        # a "correct" answer that doesn't exist yet. This is exactly the
        # kind of case Sprint 3 prompt design should watch for.
        tokens = tokenize_selector("[data-testid='item-name']")
        assert tokens == ["item", "name"]