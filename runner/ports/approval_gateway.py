"""ApprovalGateway protocol port for Human-in-the-Loop verification gate (Spec 13)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runner.domain.evidence import ApprovalDecision, EvidenceCard


@runtime_checkable
class ApprovalGateway(Protocol):
    """Abstract protocol for operator approval during gatekeeper verification."""

    async def request_approval(self, card: EvidenceCard) -> ApprovalDecision:
        """Present verification evidence and wait for operator sign-off.

        Args:
            card: EvidenceCard containing test status, harness status, and evidence paths.

        Returns:
            ApprovalDecision indicating approve, reject, or diagnose.
        """
        ...
