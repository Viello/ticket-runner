"""Unit tests for the terminal intervention gateway prompts and fallbacks."""

from __future__ import annotations

from pathlib import Path
import pytest

from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway
from runner.domain.exceptions import NonInteractiveError
from runner.domain.signal import QuestionSignal, QuestionType, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.intervention import InterventionAction, InterventionDecision
from tests.fakes.fake_intervention import FakeInterventionGateway

DIAGNOSTICS = "pytest: exit code 1\nFAILED tests/unit/test_foo.py::test_bar"
ATTEMPT = 3


class RecordingInput:
    """Scriptable input() double recording every prompt it receives."""

    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._answers:
            raise AssertionError(f"No scripted input remaining; prompt was: {prompt!r}")
        return self._answers.pop(0)


class RaisingInput:
    """input() double that always raises a fixed exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __call__(self, prompt: str) -> str:
        raise self._exc


class FlakyInput:
    """input() double returning scripted answers before failing on later reads."""

    def __init__(self, answers: list[str], exc: Exception) -> None:
        self._answers = list(answers)
        self._exc = exc
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._answers:
            return self._answers.pop(0)
        raise self._exc


def make_output() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lambda text: lines.append(text)


def _ticket() -> Ticket:
    return Ticket(
        id="T029",
        title="Intervention port and terminal menu",
        status=TicketStatus.RUNNING,
        spec_path="docs/specs/04-signal-protocol-and-gatekeeper.md",
        requirements=("Define the InterventionGateway port.",),
        acceptance_criteria=("Parametrized input sequences cover the menu contract.",),
        gotchas=("Follow the non-interactive terminal fallback.",),
        path=Path("docs/tickets/04-signal-protocol-and-gatekeeper/T029.md"),
    )


def _gateway(answers: list[str]) -> tuple[TerminalInterventionGateway, RecordingInput, list[str]]:
    recording = RecordingInput(*answers)
    lines, out = make_output()
    return TerminalInterventionGateway(input_fn=recording, output_fn=out), recording, lines


def _text_question() -> QuestionSignal:
    return QuestionSignal(
        ticket_id="T029",
        question="Which database should the runner use?",
        type=QuestionType.TEXT,
        options=None,
        status=SignalStatus.PENDING,
        answer=None,
        created_at="2026-09-17T10:00:00Z",
    )


def _choice_question() -> QuestionSignal:
    return QuestionSignal(
        ticket_id="T029",
        question="Which database should the runner use?",
        type=QuestionType.CHOICE,
        options=("sqlite", "postgres"),
        status=SignalStatus.PENDING,
        answer=None,
        created_at="2026-09-17T10:00:00Z",
    )


@pytest.mark.parametrize(
    ("answers", "expected_action", "expected_hint"),
    [
        (["r"], InterventionAction.RETRY, None),
        (["R"], InterventionAction.RETRY, None),
        (["retry"], InterventionAction.RETRY, None),
        (["r use sqlite"], InterventionAction.RETRY, "use sqlite"),
        (["retry   fix   the tests"], InterventionAction.RETRY, "fix   the tests"),
        (["a"], InterventionAction.ABORT, None),
        (["abort"], InterventionAction.ABORT, None),
        (["s", "y"], InterventionAction.SKIP, None),
        (["s", "n", "a"], InterventionAction.ABORT, None),
        (["s", "", "r"], InterventionAction.RETRY, None),
        (["garbage", "r"], InterventionAction.RETRY, None),
        (["", "a"], InterventionAction.ABORT, None),
    ],
)
def test_menu_input_sequences(
    answers: list[str],
    expected_action: InterventionAction,
    expected_hint: str | None,
) -> None:
    """Verify the menu contract across case variants, hints, confirmations, and garbage."""
    gateway, recording, _ = _gateway(answers)
    decision = gateway.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)
    assert decision.action is expected_action
    assert decision.hint == expected_hint
    assert recording.prompts


def test_menu_prompt_echoes_vocabulary_diagnostics_and_attempt() -> None:
    """Verify the menu prompt carries the action vocabulary, diagnostics, and attempt number."""
    gateway, recording, lines = _gateway(["r"])
    gateway.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)
    (prompt,) = recording.prompts
    assert "[R]etry" in prompt
    assert "[S]kip" in prompt
    assert "[A]bort" in prompt
    assert DIAGNOSTICS in prompt
    assert str(ATTEMPT) in prompt
    assert "T029" in prompt
    assert lines, "expected a status line on output"
    assert "T029" in lines[0]


def test_skip_requires_confirmation_prompt() -> None:
    """Verify skip is gated behind an explicit [y/N] confirmation and declines re-prompt."""
    gateway, recording, lines = _gateway(["s", "n", "a"])
    decision = gateway.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)
    assert decision.action is InterventionAction.ABORT
    assert len(recording.prompts) == 3
    assert "[y/N]" in recording.prompts[1]
    assert any("discards uncommitted edits" in line for line in lines)


def test_question_prompt_renders_type_and_returns_raw_answer() -> None:
    """Verify text questions render their type and return the raw, uninterpreted answer."""
    gateway, recording, _ = _gateway(["  sqlite  "])
    answer = gateway.ask_question(_text_question())
    assert answer == "  sqlite  "
    (prompt,) = recording.prompts
    assert "type: text" in prompt
    assert "Which database should the runner use?" in prompt


def test_choice_question_prompt_renders_options() -> None:
    """Verify choice questions render numbered options alongside the type."""
    gateway, recording, _ = _gateway(["1"])
    answer = gateway.ask_question(_choice_question())
    assert answer == "1"
    (prompt,) = recording.prompts
    assert "type: choice" in prompt
    assert "1) sqlite" in prompt
    assert "2) postgres" in prompt


@pytest.mark.parametrize("exc", [OSError("stdin closed"), EOFError()])
def test_menu_falls_back_to_abort_when_stdin_fails(exc: Exception) -> None:
    """Verify a non-interactive stdin makes the menu return abort instead of looping."""
    gateway = TerminalInterventionGateway(input_fn=RaisingInput(exc), output_fn=lambda _: None)
    decision = gateway.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)
    assert decision.action is InterventionAction.ABORT
    assert decision.hint is None


@pytest.mark.parametrize("exc", [OSError("stdin closed"), EOFError()])
def test_question_raises_when_stdin_fails(exc: Exception) -> None:
    """Verify a non-interactive stdin raises a domain error for question prompts."""
    gateway = TerminalInterventionGateway(input_fn=RaisingInput(exc), output_fn=lambda _: None)
    with pytest.raises(NonInteractiveError):
        gateway.ask_question(_text_question())


def test_skip_confirmation_stdin_failure_declines_then_menu_aborts() -> None:
    """Verify a failing confirmation defaults to no and the subsequent menu read aborts."""
    flaky = FlakyInput(["s"], EOFError())
    gateway = TerminalInterventionGateway(input_fn=flaky, output_fn=lambda _: None)
    decision = gateway.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)
    assert decision.action is InterventionAction.ABORT
    assert len(flaky.prompts) == 3


def test_defaults_use_builtin_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the gateway defaults to the builtin input function."""
    recording = RecordingInput("r")
    monkeypatch.setattr("builtins.input", recording)
    gateway = TerminalInterventionGateway()
    decision = gateway.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)
    assert decision.action is InterventionAction.RETRY
    assert recording.prompts


def test_fake_queues_answers_and_records_prompts() -> None:
    """Verify the fake serves queued answers and records every question prompt."""
    fake = FakeInterventionGateway(answers=["A", "B"])
    assert fake.ask_question(_choice_question()) == "A"
    assert fake.ask_question(_choice_question()) == "B"
    assert [p.question for p in fake.question_prompts] == [
        "Which database should the runner use?",
        "Which database should the runner use?",
    ]


def test_fake_queues_decisions_and_records_diagnostics_payloads() -> None:
    """Verify the fake serves queued decisions and records every intervention payload."""
    fake = FakeInterventionGateway(
        decisions=[
            InterventionDecision(action=InterventionAction.RETRY, hint="use sqlite"),
            "skip",
        ]
    )
    first = fake.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)
    second = fake.request_intervention(_ticket(), "other diagnostics", 2)
    assert first.action is InterventionAction.RETRY
    assert first.hint == "use sqlite"
    assert second.action is InterventionAction.SKIP
    assert len(fake.request_records) == 2
    assert fake.request_records[0].diagnostics == DIAGNOSTICS
    assert fake.request_records[0].attempt == ATTEMPT
    assert fake.request_records[1].diagnostics == "other diagnostics"
    assert fake.request_records[1].attempt == 2


def test_fake_fails_loudly_when_exhausted() -> None:
    """Verify the fake raises rather than silently recycling when its queues run dry."""
    fake = FakeInterventionGateway(answers=[], decisions=[])
    with pytest.raises(AssertionError):
        fake.ask_question(_text_question())
    with pytest.raises(AssertionError):
        fake.request_intervention(_ticket(), DIAGNOSTICS, ATTEMPT)