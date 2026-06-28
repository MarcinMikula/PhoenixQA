"""
test_autonomous_policy.py

Unit tests for HealingBudget/AutonomousPolicy — pure tracking logic, no
live Playwright page or Ollama call needed. This is exactly the kind of
limit-enforcement logic that benefits most from isolated testing, since
getting an off-by-one wrong here means Autonomous Mode either stops too
early or — worse — doesn't stop when it should.
"""
import pytest

from phoenix.healing.autonomous_policy import AutonomousPolicy, HealingBudget


@pytest.mark.unit
class TestHealingBudgetAttempts:
    def test_starts_with_zero_consumption(self):
        budget = HealingBudget(policy=AutonomousPolicy())
        assert budget.attempts_total == 0
        assert not budget.exceeded()

    def test_record_attempt_increments_total_and_per_selector(self):
        budget = HealingBudget(policy=AutonomousPolicy())
        budget.record_attempt("[data-testid='username']")
        budget.record_attempt("[data-testid='username']")
        budget.record_attempt("[data-testid='password']")

        assert budget.attempts_total == 3
        assert budget.attempts_for("[data-testid='username']") == 2
        assert budget.attempts_for("[data-testid='password']") == 1
        assert budget.attempts_for("[data-testid='never-attempted']") == 0

    def test_total_limit_is_the_actual_stop_condition_not_per_selector(self):
        # The exact scenario from the design discussion: 4 different
        # selectors healing once each must still trip a total limit of 3,
        # even though no single selector was retried more than once.
        policy = AutonomousPolicy(max_attempts_total=3)
        budget = HealingBudget(policy=policy)

        budget.record_attempt("[data-testid='username']")
        assert not budget.exceeded()
        budget.record_attempt("[data-testid='password']")
        assert not budget.exceeded()
        budget.record_attempt("[data-testid='btn-login']")
        # Third attempt reaches the total limit, regardless of these
        # being three DIFFERENT selectors, each attempted only once.
        assert budget.exceeded()
        assert "max_attempts_total" in budget.reason_exceeded()


@pytest.mark.unit
class TestHealingBudgetTokens:
    def test_token_consumption_tracked_across_attempts(self):
        budget = HealingBudget(policy=AutonomousPolicy())
        budget.record_attempt("sel1", input_tokens=1000, output_tokens=200)
        budget.record_attempt("sel2", input_tokens=1500, output_tokens=300)

        assert budget.input_tokens_used == 2500
        assert budget.output_tokens_used == 500

    def test_input_token_limit_trips_independently_of_attempts(self):
        policy = AutonomousPolicy(max_attempts_total=100, max_input_tokens=5000)
        budget = HealingBudget(policy=policy)

        budget.record_attempt("sel1", input_tokens=4999)
        assert not budget.exceeded()
        budget.record_attempt("sel2", input_tokens=1)
        assert budget.exceeded()
        assert "max_input_tokens" in budget.reason_exceeded()

    def test_none_token_values_do_not_crash(self):
        # A provider that genuinely can't report token usage (see
        # ProviderResult docstring) should not break budget tracking.
        budget = HealingBudget(policy=AutonomousPolicy())
        budget.record_attempt("sel1", input_tokens=None, output_tokens=None)
        assert budget.input_tokens_used == 0
        assert budget.output_tokens_used == 0


@pytest.mark.unit
class TestAutonomousPolicyDefaults:
    def test_default_policy_has_sane_values(self):
        # Not testing specific numbers (those are tunable), just that
        # defaults exist and are positive — a policy with a zero or
        # negative limit would make Autonomous Mode unusable out of the box.
        policy = AutonomousPolicy()
        assert policy.min_confidence > 0
        assert policy.max_attempts_total > 0
        assert policy.max_input_tokens > 0
        assert policy.max_output_tokens > 0
        assert policy.max_time_per_heal_ms > 0

    def test_policy_is_independently_configurable(self):
        # Confirms AutonomousPolicy is a real configuration object, not
        # just hardcoded constants wearing a dataclass costume.
        strict_policy = AutonomousPolicy(min_confidence=0.95, max_attempts_total=1)
        assert strict_policy.min_confidence == 0.95
        assert strict_policy.max_attempts_total == 1
