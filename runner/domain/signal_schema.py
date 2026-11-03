"""Domain authority for the ready and question Signal schemas.

Every field of a Signal is described here as data: its name, its meaning, and a valid
example value. Renderers turn that data into a complete example payload and into the
human-readable protocol text the prompt embeds, so this module is the schema's single
authority and every other copy defers to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json

from runner.domain.runtime_paths import TICKET_ID_PATTERN, RuntimePaths

FIXED_TIMESTAMP = "2026-01-01T00:00:00Z"

_TICKET_PLACEHOLDER = "{ticket_id}"
_TIMESTAMP_PLACEHOLDER = "{timestamp}"


@dataclass(frozen=True)
class SignalFieldSpec:
    """One field of a Signal payload: its name, meaning, and example value."""

    name: str
    description: str
    example: object


READY_SIGNAL_FIELDS: tuple[SignalFieldSpec, ...] = (
    SignalFieldSpec(
        name="ticket_id",
        description="Ticket identifier; must equal the active Ticket id",
        example=_TICKET_PLACEHOLDER,
    ),
    SignalFieldSpec(
        name="status",
        description='exactly "ready_for_verification"',
        example="ready_for_verification",
    ),
    SignalFieldSpec(
        name="modified_files",
        description="repository-relative paths of every file this Ticket touched",
        example=("runner/domain/signal.py", "tests/unit/domain/test_signal.py"),
    ),
    SignalFieldSpec(
        name="self_review_notes",
        description="summary of the Standards and Spec review findings, plus Security when the ticket requires it",
        example="Reviews passed: no findings above Low; targeted tests and the full suite are green.",
    ),
    SignalFieldSpec(
        name="new_gotchas",
        description=(
            'lessons learned, each an object with non-empty "problem" and "solution" keys; '
            "plain strings are also accepted"
        ),
        example=(
            {
                "problem": "Hand-maintained Signal schemas drifted from the parser.",
                "solution": "Render the schema from the domain authority.",
            },
        ),
    ),
    SignalFieldSpec(
        name="timestamp",
        description="ISO-8601 UTC timestamp of this ready Signal",
        example=_TIMESTAMP_PLACEHOLDER,
    ),
    SignalFieldSpec(
        name="scope",
        description=(
            "optional lowercase layer token (omit or null to use the queue scope; "
            "never a ticket number)"
        ),
        example="domain",
    ),
)


QUESTION_SIGNAL_FIELDS: tuple[SignalFieldSpec, ...] = (
    SignalFieldSpec(
        name="ticket_id",
        description="Ticket identifier; must equal the active Ticket id",
        example=_TICKET_PLACEHOLDER,
    ),
    SignalFieldSpec(
        name="question",
        description="the single clarifying question the Worker is blocked on",
        example="Skeleton placeholder rows or a centered spinner?",
    ),
    SignalFieldSpec(
        name="type",
        description='either "choice" or "text"',
        example="choice",
    ),
    SignalFieldSpec(
        name="options",
        description='choice labels when type is "choice"; null when type is "text"',
        example=("A: Skeleton placeholder rows", "B: Centered spinner"),
    ),
    SignalFieldSpec(
        name="status",
        description='"pending" while waiting, "answered" once the operator replies',
        example="pending",
    ),
    SignalFieldSpec(
        name="answer",
        description='null while status is "pending"; the operator answer when status is "answered"',
        example=None,
    ),
    SignalFieldSpec(
        name="created_at",
        description="ISO-8601 UTC timestamp of this question Signal",
        example=_TIMESTAMP_PLACEHOLDER,
    ),
)


def _require_ticket_id(ticket_id: object) -> str:
    if not isinstance(ticket_id, str) or not TICKET_ID_PATTERN.match(ticket_id):
        raise ValueError(
            f"ticket_id must match {TICKET_ID_PATTERN.pattern}, got: {ticket_id!r}"
        )
    return ticket_id


def _render_value(value: object, ticket_id: str) -> object:
    if isinstance(value, str):
        return value.replace(_TICKET_PLACEHOLDER, ticket_id).replace(
            _TIMESTAMP_PLACEHOLDER, FIXED_TIMESTAMP
        )
    if isinstance(value, Mapping):
        return {str(key): _render_value(item, ticket_id) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_render_value(item, ticket_id) for item in value]
    return value


def _render_payload(fields: tuple[SignalFieldSpec, ...], ticket_id: str) -> dict[str, object]:
    return {spec.name: _render_value(spec.example, ticket_id) for spec in fields}


def _render_protocol(
    fields: tuple[SignalFieldSpec, ...],
    ticket_id: str,
    *,
    title: str,
    signal_path: str,
    instruction: str,
) -> str:
    authority = (
        "This section is the single authority for this Signal payload schema: if the "
        "execution skill or any other document shows a different example, follow this section."
    )
    lines = [
        f"#### {title} (authoritative)",
        "",
        authority,
        "",
        f"Write `{signal_path}` {instruction}",
        "",
        "Fields:",
    ]
    for spec in fields:
        example = json.dumps(_render_value(spec.example, ticket_id))
        lines.append(f"- `{spec.name}`: {spec.description}. Example: `{example}`")
    payload = json.dumps(_render_payload(fields, ticket_id), indent=2)
    lines.extend(["", "Complete example payload:", "", "```json", payload, "```"])
    return "\n".join(lines)


def render_ready_signal_example(ticket_id: str) -> str:
    """Return a complete ready Signal JSON payload for `ticket_id`."""
    ticket = _require_ticket_id(ticket_id)
    return json.dumps(_render_payload(READY_SIGNAL_FIELDS, ticket), indent=2)


def render_question_signal_example(ticket_id: str) -> str:
    """Return a complete question Signal JSON payload for `ticket_id`."""
    ticket = _require_ticket_id(ticket_id)
    return json.dumps(_render_payload(QUESTION_SIGNAL_FIELDS, ticket), indent=2)


def render_ready_signal_protocol(ticket_id: str) -> str:
    """Return the human-readable ready Signal protocol section for `ticket_id`."""
    ticket = _require_ticket_id(ticket_id)
    signal_path = RuntimePaths().ready_signal_path(ticket).as_posix()
    return _render_protocol(
        READY_SIGNAL_FIELDS,
        ticket,
        title="Ready Signal Protocol",
        signal_path=signal_path,
        instruction=(
            "when implementation is complete and after reading `AGENTS.md` and "
            "`.agents/skills/code-review-ticket-runner/SKILL.md` with your file-reading tool to "
            "complete self-reviews, then stop working."
        ),
    )


def render_question_signal_protocol(ticket_id: str) -> str:
    """Return the human-readable question Signal protocol section for `ticket_id`."""
    ticket = _require_ticket_id(ticket_id)
    signal_path = RuntimePaths().question_path(ticket).as_posix()
    return _render_protocol(
        QUESTION_SIGNAL_FIELDS,
        ticket,
        title="Question Signal Protocol",
        signal_path=signal_path,
        instruction="when blocked, then stop working immediately instead of guessing.",
    )
