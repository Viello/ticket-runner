"""Unit tests for the domain Signal schema authority: field specs and renderers."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
import json

import pytest

from runner.domain.exceptions import SignalFormatError
from runner.domain.signal import QuestionSignal, QuestionType, ReadySignal, SignalStatus
from runner.domain.signal_schema import (
    FIXED_TIMESTAMP,
    QUESTION_SIGNAL_FIELDS,
    READY_SIGNAL_FIELDS,
    SignalFieldSpec,
    render_question_signal_example,
    render_question_signal_protocol,
    render_ready_signal_example,
    render_ready_signal_protocol,
)


def _spec_names(fields: tuple[SignalFieldSpec, ...]) -> tuple[str, ...]:
    return tuple(spec.name for spec in fields)


# --- Field spec value object ---


def test_signal_field_spec_is_a_frozen_value_object() -> None:
    spec = SignalFieldSpec(name="ticket_id", description="Ticket identity.", example="T026")

    assert spec.name == "ticket_id"
    assert spec.description == "Ticket identity."
    assert spec.example == "T026"
    with pytest.raises(FrozenInstanceError):
        spec.name = "status"  # type: ignore[misc]


# --- Reflection: the tuples are the parser's field inventory ---


def test_ready_field_specs_cover_every_parser_field_in_order() -> None:
    assert _spec_names(READY_SIGNAL_FIELDS) == tuple(ReadySignal.__dataclass_fields__)


def test_question_field_specs_cover_every_parser_field_in_order() -> None:
    assert _spec_names(QUESTION_SIGNAL_FIELDS) == tuple(QuestionSignal.__dataclass_fields__)


@pytest.mark.parametrize("fields", [READY_SIGNAL_FIELDS, QUESTION_SIGNAL_FIELDS])
def test_every_field_spec_describes_its_field(fields: tuple[SignalFieldSpec, ...]) -> None:
    for spec in fields:
        assert spec.description.strip()


# --- Rendered ready example ---


def test_rendered_ready_example_parses_through_the_real_parser() -> None:
    signal = ReadySignal.parse(render_ready_signal_example("T130"), "T130")

    assert signal.ticket_id == "T130"
    assert signal.status is SignalStatus.READY_FOR_VERIFICATION
    assert signal.timestamp == datetime.fromisoformat(FIXED_TIMESTAMP.replace("Z", "+00:00"))
    assert signal.scope == "domain"
    assert signal.modified_files
    assert signal.new_gotchas
    assert all(gotcha.startswith("Problem: ") for gotcha in signal.new_gotchas)
    assert all("\nSolution: " in gotcha for gotcha in signal.new_gotchas)


def test_rendered_ready_example_uses_the_requested_ticket_id() -> None:
    payload = json.loads(render_ready_signal_example("T901"))

    assert payload["ticket_id"] == "T901"


def test_rendered_ready_example_advertises_exactly_the_parser_fields() -> None:
    payload = json.loads(render_ready_signal_example("T130"))

    assert tuple(payload) == tuple(ReadySignal.__dataclass_fields__)


def test_rendered_ready_example_round_trips_without_a_ticket_mismatch() -> None:
    with pytest.raises(SignalFormatError, match="does not match"):
        ReadySignal.parse(render_ready_signal_example("T901"), "T902")


# --- Rendered question example ---


def test_rendered_question_example_parses_through_the_real_parser() -> None:
    signal = QuestionSignal.parse(render_question_signal_example("T130"), "T130")

    assert signal.ticket_id == "T130"
    assert signal.type is QuestionType.CHOICE
    assert signal.status is SignalStatus.PENDING
    assert signal.answer is None
    assert signal.options
    assert signal.created_at == datetime.fromisoformat(FIXED_TIMESTAMP.replace("Z", "+00:00"))


def test_rendered_question_example_advertises_exactly_the_parser_fields() -> None:
    payload = json.loads(render_question_signal_example("T130"))

    assert tuple(payload) == tuple(QuestionSignal.__dataclass_fields__)


# --- Protocol renderers ---


def test_ready_protocol_instructs_reading_code_review_ticket_runner_and_agents_md() -> None:
    protocol = render_ready_signal_protocol("T130")

    assert ".agents/skills/code-review-ticket-runner/SKILL.md" in protocol
    assert ".agents/skills/code-review/SKILL.md" not in protocol
    assert "AGENTS.md" in protocol


def test_ready_protocol_names_every_field_and_the_exact_status() -> None:
    protocol = render_ready_signal_protocol("T130")

    for spec in READY_SIGNAL_FIELDS:
        assert f"`{spec.name}`" in protocol
    assert "ready_for_verification" in protocol
    assert ".agent/signals/T130_ready.json" in protocol


def test_question_protocol_names_every_field_and_the_signal_path() -> None:
    protocol = render_question_signal_protocol("T130")

    for spec in QUESTION_SIGNAL_FIELDS:
        assert f"`{spec.name}`" in protocol
    assert ".agent/questions/T130.json" in protocol


@pytest.mark.parametrize(
    "render",
    [render_ready_signal_protocol, render_question_signal_protocol],
)
def test_protocols_declare_themselves_authoritative(render: object) -> None:
    protocol = render("T130")  # type: ignore[operator]

    lowered = protocol.lower()
    assert "authoritative" in lowered
    assert "execution skill" in lowered


def test_ready_protocol_embeds_an_example_that_parses() -> None:
    protocol = render_ready_signal_protocol("T130")
    body = protocol.split("```json", 1)[1].split("```", 1)[0]

    signal = ReadySignal.parse(json.loads(body), "T130")

    assert signal.status is SignalStatus.READY_FOR_VERIFICATION


def test_question_protocol_embeds_an_example_that_parses() -> None:
    protocol = render_question_signal_protocol("T130")
    body = protocol.split("```json", 1)[1].split("```", 1)[0]

    signal = QuestionSignal.parse(json.loads(body), "T130")

    assert signal.type is QuestionType.CHOICE


# --- Renderer guards ---


@pytest.mark.parametrize(
    "render",
    [
        render_ready_signal_example,
        render_ready_signal_protocol,
        render_question_signal_example,
        render_question_signal_protocol,
    ],
)
@pytest.mark.parametrize("ticket_id", ["", "   ", None, 130])
def test_renderers_reject_a_blank_or_non_string_ticket_id(
    render: object, ticket_id: object
) -> None:
    with pytest.raises(ValueError):
        render(ticket_id)  # type: ignore[operator]


@pytest.mark.parametrize(
    "render",
    [render_ready_signal_protocol, render_question_signal_protocol],
)
@pytest.mark.parametrize(
    "ticket_id",
    ["../secrets", "T130/../../escape", "T130 ready", "T130_ready.json", ".agent"],
)
def test_protocol_renderers_reject_ticket_ids_that_escape_the_agent_dir(
    render: object, ticket_id: str
) -> None:
    with pytest.raises(ValueError):
        render(ticket_id)  # type: ignore[operator]


def test_fixed_timestamp_is_a_valid_iso8601_utc_instant() -> None:
    parsed = datetime.fromisoformat(FIXED_TIMESTAMP.replace("Z", "+00:00"))

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
