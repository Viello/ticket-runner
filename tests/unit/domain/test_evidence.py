"""Unit tests for EvidenceCard and ApprovalDecision domain models."""

from dataclasses import FrozenInstanceError
from enum import Enum
import pytest

from runner.domain.evidence import ApprovalDecision, EvidenceCard


def test_approval_decision_is_enum_with_variants() -> None:
    assert issubclass(ApprovalDecision, Enum)
    assert ApprovalDecision.APPROVE.value == "approve"
    assert ApprovalDecision.REJECT.value == "reject"
    assert ApprovalDecision.DIAGNOSE.value == "diagnose"
    assert len(list(ApprovalDecision)) == 3


def test_approval_decision_reason_optional_and_callable() -> None:
    # Default reason is None
    assert ApprovalDecision.APPROVE.reason is None
    assert ApprovalDecision.REJECT.reason is None
    assert ApprovalDecision.DIAGNOSE.reason is None

    # Callable with keyword argument
    rejected = ApprovalDecision.REJECT(reason="flaky tests")
    assert isinstance(rejected, ApprovalDecision)
    assert rejected.reason == "flaky tests"
    assert rejected.value == "reject"
    assert rejected == ApprovalDecision.REJECT

    # Positional argument support
    rejected_pos = ApprovalDecision.REJECT("compile error")
    assert rejected_pos.reason == "compile error"
    assert rejected_pos == ApprovalDecision.REJECT

    # with_reason helper
    diagnosed = ApprovalDecision.DIAGNOSE.with_reason("need trace")
    assert diagnosed.reason == "need trace"
    assert diagnosed == ApprovalDecision.DIAGNOSE

    # Base instances remain unchanged (pure / immutable behavior)
    assert ApprovalDecision.REJECT.reason is None


def test_approval_decision_equality_and_hashing() -> None:
    rej1 = ApprovalDecision.REJECT(reason="err1")
    rej2 = ApprovalDecision.REJECT(reason="err2")
    assert rej1 == rej2
    assert rej1 == ApprovalDecision.REJECT
    assert rej1 == "reject"
    assert rej1 != ApprovalDecision.APPROVE

    # Hashable for set and dict operations
    s = {ApprovalDecision.APPROVE, ApprovalDecision.REJECT}
    assert ApprovalDecision.APPROVE in s
    assert rej1 in s


def test_approval_decision_coercion() -> None:
    assert ApprovalDecision("approve") == ApprovalDecision.APPROVE
    assert ApprovalDecision("reject") == ApprovalDecision.REJECT
    assert ApprovalDecision("diagnose") == ApprovalDecision.DIAGNOSE
    with pytest.raises(ValueError):
        ApprovalDecision("invalid")


def test_approval_decision_repr() -> None:
    assert repr(ApprovalDecision.APPROVE) == "<ApprovalDecision.APPROVE: 'approve'>"
    rej = ApprovalDecision.REJECT(reason="flaky")
    assert repr(rej) == "<ApprovalDecision.REJECT: 'reject' (reason='flaky')>"


def test_evidence_card_frozen_dataclass() -> None:
    card = EvidenceCard(
        ticket_id="T107",
        test_status="passed",
        harness_status="passed",
        evidence_paths=("evidence/T107/harness.log", "evidence/T107/screenshot.png"),
    )
    assert card.ticket_id == "T107"
    assert card.test_status == "passed"
    assert card.harness_status == "passed"
    assert card.evidence_paths == ("evidence/T107/harness.log", "evidence/T107/screenshot.png")
    assert not hasattr(card, "smoke_scenarios")
    assert "smoke_scenarios" not in EvidenceCard.__dataclass_fields__

    with pytest.raises(FrozenInstanceError):
        card.ticket_id = "T999"  # type: ignore[misc]


def test_evidence_card_coercion_and_defaults() -> None:
    # Coerces list to tuple for immutability
    card = EvidenceCard(
        ticket_id="T107",
        test_status="failed",
        evidence_paths=["file1.log", "file2.png"],  # type: ignore[arg-type]
    )
    assert card.harness_status is None
    assert card.evidence_paths == ("file1.log", "file2.png")


def test_evidence_card_validation() -> None:
    with pytest.raises(ValueError, match="ticket_id"):
        EvidenceCard(ticket_id="../../evil", test_status="passed")

    with pytest.raises(ValueError, match="test_status"):
        EvidenceCard(ticket_id="T107", test_status="")
