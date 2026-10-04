"""Evidence and human-in-the-loop verification domain models (Spec 13)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from runner.domain.runtime_paths import TICKET_ID_PATTERN


class ApprovalDecision(Enum):
    """Operator decision for a verified ticket in Human-in-the-Loop mode."""

    APPROVE = "approve"
    REJECT = "reject"
    DIAGNOSE = "diagnose"

    def __init__(self, value: str) -> None:
        self.reason: str | None = None

    def __call__(self, reason: str | None = None) -> ApprovalDecision:
        """Return a decision instance annotated with an optional rejection/decision reason."""
        obj = object.__new__(self.__class__)
        obj._value_ = self._value_
        obj._name_ = self._name_
        obj.reason = reason
        return obj

    def with_reason(self, reason: str | None) -> ApprovalDecision:
        """Alias to __call__ for fluent annotation."""
        return self(reason=reason)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ApprovalDecision):
            return self._value_ == other._value_
        if isinstance(other, str):
            return self._value_ == other
        return False

    def __hash__(self) -> int:
        return hash(self._value_)

    def __repr__(self) -> str:
        if self.reason:
            return f"<{self.__class__.__name__}.{self._name_}: {self._value_!r} (reason={self.reason!r})>"
        return f"<{self.__class__.__name__}.{self._name_}: {self._value_!r}>"


@dataclass(frozen=True)
class EvidenceCard:
    """Consolidated verification evidence presented for human operator sign-off."""

    ticket_id: str
    test_status: str
    harness_status: str | None = None
    evidence_paths: tuple[str, ...] = ()
    smoke_scenarios: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ticket_id, str) or not TICKET_ID_PATTERN.match(self.ticket_id):
            raise ValueError(f"Invalid ticket_id or path traversal: {self.ticket_id!r}")
        if not isinstance(self.test_status, str) or not self.test_status.strip():
            raise ValueError(f"test_status must be a non-empty string, got: {self.test_status!r}")
        if self.harness_status is not None and not isinstance(self.harness_status, str):
            raise ValueError(f"harness_status must be a string or None, got: {self.harness_status!r}")

        # Coerce collections to immutable tuples
        if not isinstance(self.evidence_paths, tuple):
            object.__setattr__(
                self,
                "evidence_paths",
                tuple(str(p) for p in self.evidence_paths),
            )
        if not isinstance(self.smoke_scenarios, tuple):
            object.__setattr__(
                self,
                "smoke_scenarios",
                tuple(self.smoke_scenarios),
            )
