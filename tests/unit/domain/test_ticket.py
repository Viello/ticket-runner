"""Unit tests for the Ticket domain entity and status enumeration."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from runner.domain.exceptions import TicketFormatError
from runner.domain.ticket import Ticket, TicketStatus


def _ticket(**overrides: object) -> Ticket:
    fields: dict[str, object] = {
        "id": "T006",
        "title": "Ticket domain entity",
        "status": TicketStatus.PENDING,
        "spec_path": "docs/specs/02-queue-and-tickets.md",
        "requirements": ("Define the entity.",),
        "acceptance_criteria": ("Invariants hold.",),
        "gotchas": ("Keep repo style.",),
        "path": Path("docs/tickets/02-queue-and-tickets/T006-ticket-entity.md"),
    }
    fields.update(overrides)
    return Ticket(**fields)  # type: ignore[arg-type]


def test_ticket_status_values() -> None:
    assert {status.value for status in TicketStatus} == {
        "pending",
        "running",
        "in_progress",
        "completed",
        "failed",
        "blocked",
        "skipped",
    }


def test_ticket_carries_all_fields() -> None:
    ticket = _ticket()

    assert ticket.id == "T006"
    assert ticket.title == "Ticket domain entity"
    assert ticket.status is TicketStatus.PENDING
    assert ticket.spec_path == "docs/specs/02-queue-and-tickets.md"
    assert ticket.requirements == ("Define the entity.",)
    assert ticket.acceptance_criteria == ("Invariants hold.",)
    assert ticket.gotchas == ("Keep repo style.",)
    assert ticket.path == Path("docs/tickets/02-queue-and-tickets/T006-ticket-entity.md")
    assert ticket.security_required is False
    assert ticket.reasoning == ""
    assert ticket.mode == "AFK"
    assert ticket.status_note is None
    assert ticket.jump_start == ()
    assert ticket.checked_criteria == frozenset()


def test_ticket_accepts_mode_values() -> None:
    assert _ticket(mode="AFK").mode == "AFK"
    assert _ticket(mode="HITL").mode == "HITL"
    assert _ticket(mode="afk").mode == "AFK"
    assert _ticket(mode="hitl").mode == "HITL"


@pytest.mark.parametrize("invalid_mode", ["bogus", "auto", 123, True, None, []])
def test_ticket_rejects_invalid_mode(invalid_mode: object) -> None:
    with pytest.raises(TicketFormatError, match="mode"):
        _ticket(mode=invalid_mode)


def test_ticket_accepts_status_note() -> None:
    assert _ticket(status_note="reviewed; Security PASSED").status_note == "reviewed; Security PASSED"
    assert _ticket(status_note=None).status_note is None


@pytest.mark.parametrize("invalid_note", [123, True, [], {}])
def test_ticket_rejects_invalid_status_note(invalid_note: object) -> None:
    with pytest.raises(TicketFormatError, match="status_note"):
        _ticket(status_note=invalid_note)


def test_ticket_accepts_jump_start() -> None:
    ticket = _ticket(jump_start=["path/to/file.py", "Seam: domain"])
    assert ticket.jump_start == ("path/to/file.py", "Seam: domain")


def test_ticket_rejects_single_string_for_jump_start() -> None:
    with pytest.raises(TicketFormatError, match="jump_start"):
        _ticket(jump_start="path/to/file.py")


def test_ticket_accepts_checked_criteria() -> None:
    ticket = _ticket(checked_criteria=["Invariants hold."])
    assert ticket.checked_criteria == frozenset({"Invariants hold."})


@pytest.mark.parametrize("invalid_criteria", ["Invariants hold.", 123, [123]])
def test_ticket_rejects_invalid_checked_criteria(invalid_criteria: object) -> None:
    with pytest.raises(TicketFormatError, match="checked_criteria"):
        _ticket(checked_criteria=invalid_criteria)



def test_ticket_accepts_explicit_reasoning() -> None:
    assert _ticket(reasoning="high").reasoning == "high"
    assert _ticket(reasoning="").reasoning == ""


@pytest.mark.parametrize("invalid_value", [123, True, False, None, [], {}])
def test_ticket_rejects_non_str_reasoning(invalid_value: object) -> None:
    with pytest.raises(TicketFormatError, match="reasoning"):
        _ticket(reasoning=invalid_value)



def test_ticket_accepts_explicit_security_required() -> None:
    assert _ticket(security_required=True).security_required is True
    assert _ticket(security_required=False).security_required is False


@pytest.mark.parametrize("invalid_value", ["required", "True", "False", 1, 0, None, []])
def test_ticket_rejects_non_bool_security_required(invalid_value: object) -> None:
    with pytest.raises(TicketFormatError, match="security_required"):
        _ticket(security_required=invalid_value)


@pytest.mark.parametrize("status", ["pending", "running", "completed", "skipped"])
def test_ticket_accepts_string_status(status: str) -> None:
    assert _ticket(status=status).status is TicketStatus(status)


def test_ticket_rejects_unknown_status() -> None:
    with pytest.raises(TicketFormatError, match="bogus"):
        _ticket(status="bogus")


@pytest.mark.parametrize(
    "ticket_id",
    ["", "006", "T6", "T006a", "T AB1", "X006", "T-006"],
)
def test_ticket_rejects_malformed_identifier(ticket_id: str) -> None:
    with pytest.raises(TicketFormatError, match="identifier"):
        _ticket(id=ticket_id)


def test_ticket_accepts_longer_identifiers() -> None:
    assert _ticket(id="T1000").id == "T1000"


@pytest.mark.parametrize("title", ["", "   "])
def test_ticket_rejects_empty_title(title: str) -> None:
    with pytest.raises(TicketFormatError, match="title"):
        _ticket(title=title)


@pytest.mark.parametrize("spec_path", ["", "   "])
def test_ticket_rejects_empty_spec_path(spec_path: str) -> None:
    with pytest.raises(TicketFormatError, match="spec"):
        _ticket(spec_path=spec_path)


def test_ticket_coerces_section_sequences_to_tuples() -> None:
    ticket = _ticket(requirements=["one"], acceptance_criteria=["two"], gotchas=["three"])

    assert ticket.requirements == ("one",)
    assert ticket.acceptance_criteria == ("two",)
    assert ticket.gotchas == ("three",)


@pytest.mark.parametrize("field", ["requirements", "acceptance_criteria", "gotchas"])
def test_ticket_rejects_string_for_section_fields(field: str) -> None:
    with pytest.raises(TicketFormatError, match="tuple"):
        _ticket(**{field: "not a sequence"})


def test_ticket_coerces_string_path_to_path() -> None:
    ticket = _ticket(path="docs/tickets/02-queue-and-tickets/T006-ticket-entity.md")

    assert ticket.path == Path("docs/tickets/02-queue-and-tickets/T006-ticket-entity.md")


def test_ticket_is_frozen() -> None:
    ticket = _ticket()

    with pytest.raises(FrozenInstanceError):
        ticket.status = TicketStatus.RUNNING  # type: ignore[misc]
