"""FakeApprovalGateway test double for scripted human approval decisions (Spec 13)."""

from __future__ import annotations

from collections.abc import Sequence

from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.ports.approval_gateway import ApprovalGateway


class FakeApprovalGateway(ApprovalGateway):
    """In-memory ApprovalGateway serving queued approval decisions.

    Records received EvidenceCards in `.received_cards`.
    Replays pre-scripted decisions in order.
    Raises IndexError when decisions are exhausted (fail-fast in tests).
    """

    def __init__(
        self,
        decisions: Sequence[ApprovalDecision | str] | None = None,
    ) -> None:
        self._decisions: list[ApprovalDecision] = [
            self._coerce(decision) for decision in (decisions or [])
        ]
        self.received_cards: list[EvidenceCard] = []

    @staticmethod
    def _coerce(decision: ApprovalDecision | str) -> ApprovalDecision:
        if isinstance(decision, ApprovalDecision):
            return decision
        return ApprovalDecision(decision)

    async def request_approval(self, card: EvidenceCard) -> ApprovalDecision:
        """Record the evidence card and return the next scripted decision."""
        self.received_cards.append(card)
        if not self._decisions:
            raise IndexError("FakeApprovalGateway decisions exhausted")
        return self._decisions.pop(0)
