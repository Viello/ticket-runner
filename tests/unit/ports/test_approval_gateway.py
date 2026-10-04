"""Unit tests for ApprovalGateway port protocol and FakeApprovalGateway test double (T108)."""

from __future__ import annotations

import inspect
import pytest

from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.ports import ApprovalGateway
import runner.ports.approval_gateway as port_module
from tests.fakes import FakeApprovalGateway


def test_approval_gateway_protocol_definition() -> None:
    """ApprovalGateway protocol defines request_approval coroutine and has zero adapter imports."""
    methods = dict(inspect.getmembers(ApprovalGateway, predicate=inspect.isfunction))
    assert "request_approval" in methods
    assert inspect.iscoroutinefunction(ApprovalGateway.request_approval)

    source = inspect.getsource(port_module)
    assert "runner.adapters" not in source


def test_fake_approval_gateway_conforms_to_protocol() -> None:
    """FakeApprovalGateway satisfies the runtime-checkable ApprovalGateway protocol."""
    fake = FakeApprovalGateway()
    assert isinstance(fake, ApprovalGateway)


@pytest.mark.anyio
async def test_fake_approval_gateway_replay_and_recording() -> None:
    """FakeApprovalGateway records received cards and replays decisions in sequence."""
    decisions = [
        ApprovalDecision.REJECT.with_reason("Incomplete smoke log"),
        ApprovalDecision.APPROVE,
    ]
    fake = FakeApprovalGateway(decisions=decisions)
    assert fake.received_cards == []

    card1 = EvidenceCard(
        ticket_id="T108",
        test_status="passed",
        evidence_paths=("/evidence/1",),
    )
    result1 = await fake.request_approval(card1)
    assert result1 == ApprovalDecision.REJECT
    assert result1.reason == "Incomplete smoke log"
    assert fake.received_cards == [card1]

    card2 = EvidenceCard(
        ticket_id="T108",
        test_status="passed",
        evidence_paths=("/evidence/2",),
    )
    result2 = await fake.request_approval(card2)
    assert result2 == ApprovalDecision.APPROVE
    assert fake.received_cards == [card1, card2]


@pytest.mark.anyio
async def test_fake_approval_gateway_string_coercion() -> None:
    """FakeApprovalGateway accepts string decision names and coerces them to ApprovalDecision."""
    fake = FakeApprovalGateway(decisions=["approve", "diagnose"])
    card = EvidenceCard(ticket_id="T108", test_status="passed")

    decision1 = await fake.request_approval(card)
    assert decision1 == ApprovalDecision.APPROVE
    assert isinstance(decision1, ApprovalDecision)

    decision2 = await fake.request_approval(card)
    assert decision2 == ApprovalDecision.DIAGNOSE
    assert isinstance(decision2, ApprovalDecision)


@pytest.mark.anyio
async def test_fake_approval_gateway_exhaustion_raises_index_error() -> None:
    """FakeApprovalGateway raises IndexError when scripted decisions are exhausted."""
    fake = FakeApprovalGateway(decisions=[])
    card = EvidenceCard(ticket_id="T108", test_status="passed")

    with pytest.raises(IndexError, match="exhausted"):
        await fake.request_approval(card)


@pytest.mark.anyio
async def test_fake_approval_gateway_exhaustion_after_consumption() -> None:
    """FakeApprovalGateway raises IndexError on the N+1 call after exhausting all decisions."""
    fake = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])
    card = EvidenceCard(ticket_id="T108", test_status="passed")

    decision = await fake.request_approval(card)
    assert decision == ApprovalDecision.APPROVE

    with pytest.raises(IndexError, match="exhausted"):
        await fake.request_approval(card)
