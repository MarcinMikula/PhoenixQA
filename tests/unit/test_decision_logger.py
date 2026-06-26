"""
test_decision_logger.py

Unit tests for log_decision. Pure file I/O — no live Playwright page or
Ollama call needed, unlike the rest of Sprint 4 (Healer/safe_mode require
a real browser page and a real LLM round-trip, so they're exercised via
manual integration testing against Chaos App, not here).
"""
import json

import pytest

from phoenix.ai.base_provider import HealingContext, HealingProposal
from phoenix.collector.failure_classifier import FailureType
from phoenix.healing.decision_logger import log_decision


def _sample_context():
    return HealingContext(
        broken_selector="[data-testid='username-ab12']",
        error_message="Timeout 10000ms exceeded waiting for locator",
        dom_snapshot="<form>...</form>",
        page_url="http://localhost:5173/",
        original_code="fill",
        failure_type=FailureType.SELECTOR_NOT_FOUND,
    )


def _sample_proposal():
    return HealingProposal(
        proposed_selector="[data-testid='username-x7f2']",
        confidence=0.92,
        reasoning="Same form position, matching data-testid prefix",
        alternative_selectors=["#chaos-username"],
        raw_response='{"proposed_selector": "..."}',
    )


@pytest.mark.unit
class TestLogDecision:
    def test_writes_one_json_line_with_expected_fields(self, tmp_path):
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=True, log_path=str(log_path))

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["broken_selector"] == "[data-testid='username-ab12']"
        assert entry["proposed_selector"] == "[data-testid='username-x7f2']"
        assert entry["confidence"] == 0.92
        assert entry["accepted"] is True
        assert entry["failure_type"] == "selector_not_found"
        assert entry["mode"] == "safe"
        assert "timestamp" in entry

    def test_appends_rather_than_overwrites(self, tmp_path):
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=True, log_path=str(log_path))
        log_decision(_sample_context(), _sample_proposal(), accepted=False, log_path=str(log_path))

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["accepted"] is True
        assert second["accepted"] is False

    def test_rejected_decision_is_logged_too_not_just_accepted(self, tmp_path):
        # The log needs the full picture for post-hoc review (per direct
        # discussion) — rejections are just as important to trace as
        # acceptances, not a silent path.
        log_path = tmp_path / "healing_decisions.log"
        log_decision(_sample_context(), _sample_proposal(), accepted=False, log_path=str(log_path))

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["accepted"] is False
        assert entry["reasoning"] == "Same form position, matching data-testid prefix"
