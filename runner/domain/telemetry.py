"""Token telemetry and budget monitor domain models and invariants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from runner.domain.config import TokenBudgetConfig


class BudgetAction(str, Enum):
    """Budget threshold actions emitted by BudgetMonitor."""

    WARN = "warn"
    HANDOFF = "handoff"
    CEILING = "ceiling"


@dataclass(frozen=True)
class TokenUsage:
    """Token consumption telemetry for a single step or cumulative snapshot.

    Follows ADR 0015 context-occupancy calculation rules:
    When total is present in the stream event, occupancy equals total.
    Otherwise, occupancy is calculated as:
    input + output + reasoning + cache_read + cache_write.
    """

    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("input", "output", "reasoning", "cache_read", "cache_write"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"TokenUsage {field_name} must be an integer, got {type(value).__name__}"
                )
            if value < 0:
                raise ValueError(
                    f"TokenUsage {field_name} must be a non-negative integer, got {value}"
                )

        if self.total is not None:
            if not isinstance(self.total, int) or isinstance(self.total, bool):
                raise TypeError(
                    f"TokenUsage total must be an integer or None, got {type(self.total).__name__}"
                )
            if self.total < 0:
                raise ValueError(
                    f"TokenUsage total must be a non-negative integer, got {self.total}"
                )

    @property
    def occupancy(self) -> int:
        """Current context-window occupancy in tokens per ADR 0015."""
        if self.total is not None:
            return self.total
        return (
            self.input
            + self.output
            + self.reasoning
            + self.cache_read
            + self.cache_write
        )


def effective_ceiling(
    configured: int | TokenBudgetConfig,
    model_limit: int | None = None,
) -> int:
    """Calculate the effective token ceiling.

    Returns min(configured, model_limit) when model_limit is supplied,
    otherwise returns the configured ceiling value (ADR 0015).

    Args:
        configured: Configured ceiling integer or a TokenBudgetConfig instance.
        model_limit: Optional model context window limit.

    Returns:
        The effective ceiling as a positive integer.
    """
    if isinstance(configured, TokenBudgetConfig):
        ceiling = configured.ceiling
    elif isinstance(configured, int) and not isinstance(configured, bool):
        ceiling = configured
    else:
        raise TypeError(
            f"configured must be an int or TokenBudgetConfig, got {type(configured).__name__}"
        )

    if ceiling <= 0:
        raise ValueError(f"Configured ceiling must be a positive integer, got: {ceiling}")

    if model_limit is not None:
        if not isinstance(model_limit, int) or isinstance(model_limit, bool):
            raise TypeError(
                f"model_limit must be an integer or None, got {type(model_limit).__name__}"
            )
        if model_limit <= 0:
            raise ValueError(f"model_limit must be a positive integer, got: {model_limit}")
        return min(ceiling, model_limit)

    return ceiling


class BudgetMonitor:
    """Monitors token usage occupancy against configured budget thresholds.

    Semantics:
    - WARN fires exactly once per Ticket supervision chain on first crossing warn.
    - HANDOFF fires once when occupancy >= handoff.
    - CEILING wins when occupancy >= effective ceiling.
    - When one update crosses several thresholds, the highest-priority action
      is returned while lower threshold reminders (WARN, HANDOFF) are recorded
      as already sent.
    - Reset only by constructing a fresh monitor instance.
    """

    def __init__(
        self,
        config: TokenBudgetConfig | None = None,
        model_limit: int | None = None,
    ) -> None:
        self._config = config if config is not None else TokenBudgetConfig()
        if not isinstance(self._config, TokenBudgetConfig):
            raise TypeError(
                f"config must be a TokenBudgetConfig instance, got {type(self._config).__name__}"
            )

        self._model_limit = model_limit
        self._effective_ceiling = effective_ceiling(
            self._config.ceiling, model_limit=model_limit
        )

        self._warn_sent: bool = False
        self._handoff_sent: bool = False
        self._ceiling_hit: bool = False

        self._latest_occupancy: int = 0
        self._highest_occupancy: int = 0
        self._latest_usage: TokenUsage | None = None

    @property
    def config(self) -> TokenBudgetConfig:
        """Configured token budget thresholds."""
        return self._config

    @property
    def effective_ceiling(self) -> int:
        """Effective ceiling after applying model limits."""
        return self._effective_ceiling

    @property
    def warn_threshold(self) -> int:
        """Token threshold for warning."""
        return self._config.warn

    @property
    def handoff_threshold(self) -> int:
        """Token threshold for handoff."""
        return self._config.handoff

    @property
    def ceiling_threshold(self) -> int:
        """Token threshold for ceiling termination."""
        return self._effective_ceiling

    @property
    def warned(self) -> bool:
        """Whether the warning threshold has fired or been marked sent."""
        return self._warn_sent

    @property
    def handed_off(self) -> bool:
        """Whether the handoff threshold has fired or been marked sent."""
        return self._handoff_sent

    @property
    def ceiling_hit(self) -> bool:
        """Whether the ceiling threshold has been reached."""
        return self._ceiling_hit

    @property
    def latest_occupancy(self) -> int:
        """Most recently observed token occupancy."""
        return self._latest_occupancy

    @property
    def highest_occupancy(self) -> int:
        """Highest token occupancy observed across the supervision chain."""
        return self._highest_occupancy

    @property
    def latest_usage(self) -> TokenUsage | None:
        """Most recently observed TokenUsage instance."""
        return self._latest_usage

    def observe(self, usage: TokenUsage) -> BudgetAction | None:
        """Observe token usage and report budget action if a threshold is crossed.

        Args:
            usage: Observed TokenUsage domain entity.

        Returns:
            BudgetAction if an action is triggered, else None.
        """
        if not isinstance(usage, TokenUsage):
            raise TypeError(
                f"usage must be a TokenUsage instance, got {type(usage).__name__}"
            )

        occupancy = usage.occupancy
        self._latest_usage = usage
        self._latest_occupancy = occupancy
        if occupancy > self._highest_occupancy:
            self._highest_occupancy = occupancy

        if occupancy >= self._effective_ceiling:
            self._ceiling_hit = True
            self._warn_sent = True
            self._handoff_sent = True
            return BudgetAction.CEILING

        if occupancy >= self._config.handoff:
            self._warn_sent = True
            if not self._handoff_sent:
                self._handoff_sent = True
                return BudgetAction.HANDOFF
            return None

        if occupancy >= self._config.warn:
            if not self._warn_sent:
                self._warn_sent = True
                return BudgetAction.WARN
            return None

        return None
