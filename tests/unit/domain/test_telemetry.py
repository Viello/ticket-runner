"""Unit tests for token telemetry and budget monitor domain models."""

from dataclasses import FrozenInstanceError
import pytest

from runner.domain.config import TokenBudgetConfig
from runner.domain.telemetry import (
    BudgetAction,
    BudgetMonitor,
    TokenUsage,
    effective_ceiling,
)


# --- TokenUsage & Occupancy Tests ---


def test_token_usage_defaults_and_fields() -> None:
    usage = TokenUsage()
    assert usage.input == 0
    assert usage.output == 0
    assert usage.reasoning == 0
    assert usage.cache_read == 0
    assert usage.cache_write == 0
    assert usage.total is None
    assert usage.occupancy == 0


def test_token_usage_explicit_values() -> None:
    usage = TokenUsage(
        input=1000,
        output=200,
        reasoning=150,
        cache_read=500,
        cache_write=50,
        total=1900,
    )
    assert usage.input == 1000
    assert usage.output == 200
    assert usage.reasoning == 150
    assert usage.cache_read == 500
    assert usage.cache_write == 50
    assert usage.total == 1900
    assert usage.occupancy == 1900


def test_token_usage_immutability() -> None:
    usage = TokenUsage(input=100)
    with pytest.raises(FrozenInstanceError):
        usage.input = 200  # type: ignore[misc]


def test_token_usage_occupancy_total_precedence() -> None:
    # When total is provided, occupancy uses total even if it differs from the sum
    usage = TokenUsage(
        input=10,
        output=20,
        reasoning=30,
        cache_read=40,
        cache_write=50,
        total=500,
    )
    assert usage.occupancy == 500

    # total=0 is a valid present total
    usage_zero = TokenUsage(input=10, output=20, total=0)
    assert usage_zero.occupancy == 0


def test_token_usage_occupancy_calculated_when_total_none() -> None:
    # When total is None, occupancy is input + output + reasoning + cache_read + cache_write
    usage = TokenUsage(
        input=100,
        output=20,
        reasoning=10,
        cache_read=30,
        cache_write=5,
        total=None,
    )
    assert usage.occupancy == 165


def test_token_usage_occupancy_realistic_opencode_payload() -> None:
    # Realistic OpenCode / provider payload (ADR 0015 gotcha):
    # tokens.input excludes cache read/write in per-step provider streams.
    # Total context occupancy must sum all components to avoid undercounting.
    usage = TokenUsage(
        input=45000,
        cache_read=80000,
        cache_write=5000,
        reasoning=2000,
        output=3000,
        total=None,
    )
    assert usage.occupancy == 135000


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"input": -1}, "input"),
        ({"output": -5}, "output"),
        ({"reasoning": -10}, "reasoning"),
        ({"cache_read": -2}, "cache_read"),
        ({"cache_write": -3}, "cache_write"),
        ({"total": -100}, "total"),
        ({"input": "100"}, "input"),
        ({"output": 1.5}, "output"),
    ],
)
def test_token_usage_invalid_values(kwargs: dict[str, object], match: str) -> None:
    with pytest.raises((ValueError, TypeError), match=match):
        TokenUsage(**kwargs)  # type: ignore[arg-type]


# --- effective_ceiling Tests ---


def test_effective_ceiling_without_model_limit() -> None:
    assert effective_ceiling(150000) == 150000
    assert effective_ceiling(150000, model_limit=None) == 150000


def test_effective_ceiling_with_token_budget_config() -> None:
    cfg = TokenBudgetConfig(warn=120000, handoff=135000, ceiling=150000)
    assert effective_ceiling(cfg) == 150000
    assert effective_ceiling(cfg, model_limit=140000) == 140000
    assert effective_ceiling(cfg, model_limit=160000) == 150000


def test_effective_ceiling_with_model_limit() -> None:
    # model_limit smaller than configured -> returns model_limit
    assert effective_ceiling(150000, model_limit=100000) == 100000
    # model_limit larger than configured -> returns configured
    assert effective_ceiling(150000, model_limit=200000) == 150000
    # model_limit equal to configured -> returns configured
    assert effective_ceiling(150000, model_limit=150000) == 150000


@pytest.mark.parametrize(
    ("configured", "model_limit"),
    [
        (-1, None),
        (0, None),
        (150000, 0),
        (150000, -100),
    ],
)
def test_effective_ceiling_invalid_values(
    configured: int, model_limit: int | None
) -> None:
    with pytest.raises(ValueError):
        effective_ceiling(configured, model_limit=model_limit)


def test_effective_ceiling_invalid_types() -> None:
    with pytest.raises(TypeError):
        effective_ceiling("150000")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        effective_ceiling(150000, model_limit="100000")  # type: ignore[arg-type]


# --- BudgetAction Enum Tests ---


def test_budget_action_values() -> None:
    assert BudgetAction.WARN.value == "warn"
    assert BudgetAction.HANDOFF.value == "handoff"
    assert BudgetAction.CEILING.value == "ceiling"


# --- BudgetMonitor Tests ---


def test_budget_monitor_initial_state() -> None:
    monitor = BudgetMonitor()
    assert monitor.config.warn == 120000
    assert monitor.config.handoff == 135000
    assert monitor.config.ceiling == 150000
    assert monitor.effective_ceiling == 150000
    assert monitor.warn_threshold == 120000
    assert monitor.handoff_threshold == 135000
    assert monitor.ceiling_threshold == 150000
    assert monitor.warned is False
    assert monitor.handed_off is False
    assert monitor.ceiling_hit is False
    assert monitor.latest_occupancy == 0
    assert monitor.highest_occupancy == 0
    assert monitor.latest_usage is None


def test_budget_monitor_gradual_threshold_progression() -> None:
    monitor = BudgetMonitor()

    # Step 1: Sub-threshold (below 120k)
    assert monitor.observe(TokenUsage(total=50000)) is None
    assert monitor.warned is False
    assert monitor.handed_off is False
    assert monitor.ceiling_hit is False
    assert monitor.latest_occupancy == 50000
    assert monitor.highest_occupancy == 50000

    # Step 2: Crossing warn threshold (120k)
    assert monitor.observe(TokenUsage(total=120000)) == BudgetAction.WARN
    assert monitor.warned is True
    assert monitor.handed_off is False
    assert monitor.ceiling_hit is False

    # Step 3: Above warn but below handoff (WARN must NOT re-fire)
    assert monitor.observe(TokenUsage(total=125000)) is None
    assert monitor.observe(TokenUsage(total=134999)) is None
    assert monitor.warned is True
    assert monitor.handed_off is False

    # Step 4: Crossing handoff threshold (135k)
    assert monitor.observe(TokenUsage(total=135000)) == BudgetAction.HANDOFF
    assert monitor.warned is True
    assert monitor.handed_off is True
    assert monitor.ceiling_hit is False

    # Step 5: Above handoff but below ceiling (HANDOFF must NOT re-fire)
    assert monitor.observe(TokenUsage(total=140000)) is None
    assert monitor.observe(TokenUsage(total=149999)) is None
    assert monitor.warned is True
    assert monitor.handed_off is True

    # Step 6: Crossing ceiling threshold (150k)
    assert monitor.observe(TokenUsage(total=150000)) == BudgetAction.CEILING
    assert monitor.ceiling_hit is True

    # Step 7: Subsequent checks at or above ceiling continue to report CEILING
    assert monitor.observe(TokenUsage(total=155000)) == BudgetAction.CEILING
    assert monitor.highest_occupancy == 155000


def test_budget_monitor_jump_across_warn_and_handoff() -> None:
    # First update skips warn (120k) and lands in handoff (>= 135k)
    monitor = BudgetMonitor()
    action = monitor.observe(TokenUsage(total=140000))

    # Highest-priority action (HANDOFF) is returned
    assert action == BudgetAction.HANDOFF
    # WARN is recorded as already-sent
    assert monitor.warned is True
    assert monitor.handed_off is True
    assert monitor.ceiling_hit is False

    # Subsequent update does not re-fire WARN or HANDOFF
    assert monitor.observe(TokenUsage(total=145000)) is None


def test_budget_monitor_jump_across_all_thresholds() -> None:
    # First update skips warn and handoff, directly hitting ceiling (>= 150k)
    monitor = BudgetMonitor()
    action = monitor.observe(TokenUsage(total=155000))

    # CEILING wins when occupancy >= ceiling
    assert action == BudgetAction.CEILING
    # Both WARN and HANDOFF reminders are recorded as already-sent
    assert monitor.warned is True
    assert monitor.handed_off is True
    assert monitor.ceiling_hit is True


def test_budget_monitor_resumed_session_monotonicity() -> None:
    # Simulates a chain across sessions:
    # Session A reports 125k (emits WARN).
    monitor = BudgetMonitor()
    assert monitor.observe(TokenUsage(total=125000)) == BudgetAction.WARN

    # Session B resumes on the same chain (using the same monitor).
    # Resumed session reports a larger occupancy (130k). It does not re-fire WARN.
    assert monitor.observe(TokenUsage(total=130000)) is None

    # Resumed session then crosses handoff threshold. It immediately reports HANDOFF.
    assert monitor.observe(TokenUsage(total=136000)) == BudgetAction.HANDOFF

    # Resumed session continues to 142k. HANDOFF does not re-fire.
    assert monitor.observe(TokenUsage(total=142000)) is None

    # Resumed session hits ceiling. It immediately reports CEILING.
    assert monitor.observe(TokenUsage(total=151000)) == BudgetAction.CEILING


def test_budget_monitor_reset_only_by_fresh_instance() -> None:
    monitor = BudgetMonitor()
    assert monitor.observe(TokenUsage(total=125000)) == BudgetAction.WARN
    assert monitor.observe(TokenUsage(total=125000)) is None

    # Constructing a fresh monitor resets the supervision chain
    fresh_monitor = BudgetMonitor()
    assert fresh_monitor.warned is False
    assert fresh_monitor.observe(TokenUsage(total=125000)) == BudgetAction.WARN


def test_budget_monitor_custom_thresholds() -> None:
    custom_config = TokenBudgetConfig(warn=50000, handoff=70000, ceiling=90000)
    monitor = BudgetMonitor(config=custom_config)

    assert monitor.observe(TokenUsage(total=40000)) is None
    assert monitor.observe(TokenUsage(total=50000)) == BudgetAction.WARN
    assert monitor.observe(TokenUsage(total=60000)) is None
    assert monitor.observe(TokenUsage(total=70000)) == BudgetAction.HANDOFF
    assert monitor.observe(TokenUsage(total=80000)) is None
    assert monitor.observe(TokenUsage(total=90000)) == BudgetAction.CEILING


def test_budget_monitor_with_model_limit_capping_ceiling() -> None:
    custom_config = TokenBudgetConfig(warn=50000, handoff=70000, ceiling=100000)
    # Model limit is 80k, which is lower than configured ceiling of 100k
    monitor = BudgetMonitor(config=custom_config, model_limit=80000)

    assert monitor.effective_ceiling == 80000
    assert monitor.ceiling_threshold == 80000

    assert monitor.observe(TokenUsage(total=55000)) == BudgetAction.WARN
    assert monitor.observe(TokenUsage(total=72000)) == BudgetAction.HANDOFF
    assert monitor.observe(TokenUsage(total=75000)) is None
    # 80k hits effective ceiling
    assert monitor.observe(TokenUsage(total=80000)) == BudgetAction.CEILING


def test_budget_monitor_occupancy_fluctuation_monotonicity() -> None:
    # Verify that if occupancy decreases and increases again, WARN and HANDOFF do not re-fire
    monitor = BudgetMonitor()

    assert monitor.observe(TokenUsage(total=122000)) == BudgetAction.WARN
    assert monitor.observe(TokenUsage(total=110000)) is None
    assert monitor.observe(TokenUsage(total=124000)) is None

    assert monitor.observe(TokenUsage(total=136000)) == BudgetAction.HANDOFF
    assert monitor.observe(TokenUsage(total=130000)) is None
    assert monitor.observe(TokenUsage(total=137000)) is None


def test_budget_monitor_rejects_invalid_usage_type() -> None:
    monitor = BudgetMonitor()
    with pytest.raises(TypeError, match="TokenUsage"):
        monitor.observe("not-a-token-usage")  # type: ignore[arg-type]
