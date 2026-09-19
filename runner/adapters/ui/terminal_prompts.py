"""Terminal adapter rendering human prompts over the InterventionGateway port."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import sys

from runner.domain.exceptions import NonInteractiveError
from runner.domain.signal import QuestionSignal, QuestionType
from runner.domain.ticket import Ticket
from runner.ports.intervention import (
    InterventionAction,
    InterventionDecision,
    InterventionGateway,
)

_RETRY_WORDS = ("r", "retry")
_SKIP_WORDS = ("s", "skip")
_ABORT_WORDS = ("a", "abort")
_CONFIRM_WORDS = ("y", "yes")

_INTERACTIVE_FAILURES = (OSError, EOFError)


class TerminalInterventionGateway:
    """InterventionGateway backed by interactive terminal prompts.

    Args:
        input_fn: Callable reading one line from the human; defaults to input().
        output_fn: Callable emitting status lines; defaults to print().
    """

    def __init__(
        self,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._input_fn = input_fn if input_fn is not None else input
        self._output_fn = output_fn if output_fn is not None else print

    def _read_line(self, prompt: str) -> str | None:
        """Read one line, mapping non-interactive stdin failures to None."""
        try:
            return self._input_fn(prompt)
        except _INTERACTIVE_FAILURES:
            return None

    def _render_question(self, question: QuestionSignal) -> str:
        header = (
            f"[Question] {question.ticket_id}: {question.question} "
            f"(type: {question.type.value})"
        )
        if question.type is QuestionType.CHOICE:
            options = "\n".join(
                f"{index + 1}) {option}"
                for index, option in enumerate(question.options or ())
            )
            return f"{header}\nOptions:\n{options}\nAnswer: "
        return f"{header}\nAnswer: "

    def _render_menu(self, ticket: Ticket, diagnostics: str, attempt: int) -> str:
        return (
            f"[Intervention] Ticket {ticket.id} failed verification after "
            f"{attempt} attempt(s).\n"
            f"--- diagnostics ---\n{diagnostics}\n---\n"
            "[R]etry [hint] | [S]kip | [A]bort: "
        )

    @staticmethod
    def _parse_menu_input(raw: str) -> tuple[InterventionAction | None, str | None]:
        text = raw.strip()
        if not text:
            return None, None
        parts = text.split(maxsplit=1)
        word = parts[0].lower()
        hint = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        if word in _RETRY_WORDS:
            return InterventionAction.RETRY, hint
        if word in _SKIP_WORDS:
            return InterventionAction.SKIP, None
        if word in _ABORT_WORDS:
            return InterventionAction.ABORT, None
        return None, None

    def ask_question(self, question: QuestionSignal) -> str:
        """Prompt the human and return the raw answer text without interpretation."""
        answer = self._read_line(self._render_question(question))
        if answer is None:
            raise NonInteractiveError(
                f"Cannot prompt question for ticket {question.ticket_id}: "
                "stdin is not interactive"
            )
        return answer

    def request_intervention(
        self, ticket: Ticket, diagnostics: str, attempt: int
    ) -> InterventionDecision:
        """Open the intervention menu, re-prompting until a valid decision is made.

        Non-interactive stdin falls back to abort so the Runner never silently
        continues; an unrecognized input or a declined skip confirmation re-prompts.
        """
        self._output_fn(
            f"[Intervention] Ticket {ticket.id} failed verification after "
            f"{attempt} attempt(s); human decision required."
        )
        while True:
            raw = self._read_line(self._render_menu(ticket, diagnostics, attempt))
            if raw is None:
                return InterventionDecision(action=InterventionAction.ABORT)
            action, hint = self._parse_menu_input(raw)
            if action is InterventionAction.SKIP:
                self._output_fn(
                    "[Intervention] Skip discards uncommitted edits "
                    "(git reset --hard HEAD; git clean -fd)."
                )
                confirmed = self._read_line("[S]kip confirmation [y/N]: ")
                if confirmed is None or confirmed.strip().lower() not in _CONFIRM_WORDS:
                    continue
                return InterventionDecision(action=action)
            if action is None:
                continue
            return InterventionDecision(action=action, hint=hint)


def _default_read_terminal_key() -> str:
    """Read a single raw key from console; returns empty string if unavailable."""
    if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        return ""
    try:
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # Consume multi-byte prefix
            return ""
        return ch
    except (ImportError, AttributeError, OSError, ValueError):
        return ""


class TerminalHostPrompt:
    """Renders plain-text terminal host menu and reads keystrokes to select a terminal host."""

    def __init__(
        self,
        read_key: Callable[[], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
        is_interactive: Callable[[], bool] | None = None,
    ) -> None:
        self._read_key = read_key if read_key is not None else _default_read_terminal_key
        self._output_fn = output_fn if output_fn is not None else print
        self._is_interactive = (
            is_interactive
            if is_interactive is not None
            else lambda: bool(hasattr(sys.stdin, "isatty") and sys.stdin.isatty())
        )

    def is_interactive(self) -> bool:
        """Check whether current stdin session is interactive (TTY)."""
        return self._is_interactive()

    def render_menu(self, hosts: Sequence[str]) -> str:
        """Render plain-text menu lines for candidate terminal hosts."""
        lines = ["Select terminal host for interactive sessions:"]
        for index, host in enumerate(hosts, start=1):
            lines.append(f"  [{index}] {host}")
        lines.append("> _")
        return "\n".join(lines)

    def select_host(self, hosts: Sequence[str]) -> str | None:
        """Present menu and read keystrokes until a valid host is confirmed.

        - 0 hosts: returns None silently.
        - 1 host: auto-selects silently without prompting.
        - >1 hosts non-interactive: auto-selects the first (highest-priority) host without prompting.
        - >1 hosts interactive: prints menu, reads keys until digit selects and Enter confirms.
        """
        if not hosts:
            return None
        if len(hosts) == 1:
            return hosts[0]

        if not self.is_interactive():
            return hosts[0]

        menu = self.render_menu(hosts)
        self._output_fn(menu)

        selected_host: str | None = None
        while True:
            try:
                key = self._read_key()
            except (OSError, EOFError):
                return hosts[0]

            if not key:
                return hosts[0]

            if key in ("\r", "\n"):
                if selected_host is not None:
                    return selected_host
                continue

            if key.isdigit():
                idx = int(key)
                if 1 <= idx <= len(hosts):
                    selected_host = hosts[idx - 1]
                    continue

            selected_host = None
            continue