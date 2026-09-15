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
    assert {status.value for status in TicketStatus} == {"pending", "running", "completed", "skipped"}


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
