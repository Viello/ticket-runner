"""Terminal approval adapter rendering EvidenceCards and capturing operator sign-off (Spec 13)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import io
import sys
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.domain.exceptions import NonInteractiveError
from runner.ports.approval_gateway import ApprovalGateway

_INTERACTIVE_EXCEPTIONS = (NonInteractiveError, EOFError, OSError)


def _default_read_key(target_stdin: Any = None) -> str:
    """Read a single raw key from console; raises NonInteractiveError if unavailable."""
    stream = target_stdin if target_stdin is not None else sys.stdin
    if not hasattr(stream, "isatty") or not stream.isatty():
        raise NonInteractiveError(
            "Cannot prompt for approval: stdin is not interactive"
        )
    try:
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # Consume multi-byte prefix
            return ""
        return ch
    except (ImportError, AttributeError, OSError, ValueError) as exc:
        raise NonInteractiveError(
            "Cannot prompt for approval: raw console input is unavailable"
        ) from exc


class TerminalApprovalAdapter(ApprovalGateway):
    """Terminal approval adapter implementing ApprovalGateway via Rich and console input."""

    def __init__(
        self,
        console: Console | None = None,
        read_key: Callable[[], str] | None = None,
        input_fn: Callable[[str], str] | None = None,
        stdin: Any = None,
        is_interactive: Callable[[], bool] | bool | None = None,
    ) -> None:
        self._console = console if console is not None else Console()
        self._read_key_fn = read_key
        self._input_fn = input_fn
        self._stdin = stdin
        self._is_interactive_override = is_interactive

    def is_interactive(self) -> bool:
        """Check whether the active console/stdin session is interactive."""
        if self._is_interactive_override is not None:
            if callable(self._is_interactive_override):
                return bool(self._is_interactive_override())
            return bool(self._is_interactive_override)
        if self._read_key_fn is not None:
            return True
        target = self._stdin if self._stdin is not None else sys.stdin
        if hasattr(target, "isatty"):
            try:
                return bool(target.isatty())
            except Exception:
                return False
        return False

    def render_card(self, card: EvidenceCard) -> Panel:
        """Render the EvidenceCard as a formatted Rich Panel with status, paths, and checklist."""
        elements: list[Text] = []

        # Ticket & Test status
        elements.append(Text.from_markup(f"[bold]Ticket:[/bold] {card.ticket_id}"))

        test_is_pass = card.test_status.lower() in ("passed", "pass", "ok")
        test_color = "green" if test_is_pass else "red"
        elements.append(
            Text.from_markup(
                f"[bold]Test Status:[/bold] [{test_color}]{card.test_status.upper()}[/{test_color}]"
            )
        )

        # Harness status
        if card.harness_status is not None:
            harness_is_pass = card.harness_status.lower() in ("passed", "pass", "ok")
            harness_color = "green" if harness_is_pass else "red"
            elements.append(
                Text.from_markup(
                    f"[bold]Harness Status:[/bold] [{harness_color}]{card.harness_status.upper()}[/{harness_color}]"
                )
            )

        # Evidence Paths
        elements.append(Text.from_markup("[bold]Evidence Paths:[/bold]"))
        if card.evidence_paths:
            for path in card.evidence_paths:
                elements.append(Text(f"  • {path}", overflow="fold"))
        else:
            elements.append(Text(f"  • .agent/evidence/{card.ticket_id}/", overflow="fold"))

        # Smoke Scenarios checklist
        elements.append(Text.from_markup("[bold]Smoke Scenarios:[/bold]"))
        if card.smoke_scenarios:
            for item in card.smoke_scenarios:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or "Unnamed scenario"
                    auto = " [also auto-covered]" if item.get("auto_covered") else ""
                    elements.append(Text(f"  [ ] {name}{auto}", overflow="fold"))
                elif isinstance(item, str):
                    elements.append(Text(f"  [ ] {item}", overflow="fold"))
                else:
                    elements.append(Text(f"  [ ] {item!s}", overflow="fold"))
        else:
            elements.append(Text("  (none)", style="dim"))

        # Action instructions
        elements.append(Text(""))
        elements.append(
            Text.from_markup(
                "[bold cyan]\\[y][/bold cyan] Approve & Commit   "
                "[bold red]\\[n][/bold red] Reject & Retry   "
                "[bold yellow]\\[d][/bold yellow] Diagnose"
            )
        )

        border_color = "green" if test_is_pass else "yellow"
        return Panel(
            Group(*elements),
            title=f"Verification Approval — {card.ticket_id}",
            border_style=border_color,
            expand=True,
        )

    def _read_single_key(self) -> str:
        """Read a single raw key from injected read_key, stdin, or console."""
        if self._read_key_fn is not None:
            return self._read_key_fn()
        if self._stdin is not None:
            if hasattr(self._stdin, "isatty") and not self._stdin.isatty():
                raise NonInteractiveError("stdin is not interactive")
            ch = self._stdin.read(1)
            if not ch:
                raise EOFError("EOF on stdin")
            # If line-buffered input was provided, consume any immediately following newline
            if hasattr(self._stdin, "tell") and hasattr(self._stdin, "seek"):
                pos = self._stdin.tell()
                nxt = self._stdin.read(1)
                if nxt == "\r":
                    pos2 = self._stdin.tell()
                    nxt2 = self._stdin.read(1)
                    if nxt2 != "\n":
                        self._stdin.seek(pos2)
                elif nxt != "\n":
                    self._stdin.seek(pos)
            return ch
        return _default_read_key(sys.stdin)

    def _read_line(self, prompt: str) -> str:
        """Prompt and read a line of text for rejection reason."""
        if self._input_fn is not None:
            return self._input_fn(prompt)
        if self._stdin is not None:
            if hasattr(self._stdin, "isatty") and not self._stdin.isatty():
                raise NonInteractiveError("stdin is not interactive")
            line = self._stdin.readline()
            return line.rstrip("\r\n")
        self._console.print(prompt, end="")
        try:
            return input()
        except _INTERACTIVE_EXCEPTIONS as exc:
            raise NonInteractiveError("stdin is not interactive") from exc

    async def request_approval(self, card: EvidenceCard) -> ApprovalDecision:
        """Present verification evidence and wait for operator keystroke sign-off."""
        panel = self.render_card(card)
        self._console.print(panel)

        if not self.is_interactive():
            return ApprovalDecision.REJECT("non-interactive terminal")

        await asyncio.sleep(0)

        while True:
            try:
                raw_key = self._read_single_key()
            except _INTERACTIVE_EXCEPTIONS:
                return ApprovalDecision.REJECT("non-interactive terminal")

            if not raw_key:
                return ApprovalDecision.REJECT("non-interactive terminal")

            key = raw_key.strip().lower()
            if key in ("\r", "\n", ""):
                continue

            if key == "y":
                return ApprovalDecision.APPROVE
            elif key == "d":
                return ApprovalDecision.DIAGNOSE
            elif key == "n":
                try:
                    reason = self._read_line("Rejection reason (leave blank for none): ")
                except _INTERACTIVE_EXCEPTIONS:
                    return ApprovalDecision.REJECT("non-interactive terminal")
                clean_reason = reason.strip() if reason and reason.strip() else None
                return ApprovalDecision.REJECT(clean_reason or "rejected by operator")
            else:
                self._console.print(
                    "[yellow]Invalid key. Press [y] to approve, [n] to reject, or [d] to diagnose.[/yellow]"
                )

    def request_approval_sync(self, card: EvidenceCard) -> ApprovalDecision:
        """Synchronously request approval, running request_approval on an event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: asyncio.run(self.request_approval(card)))
                return future.result()

        return asyncio.run(self.request_approval(card))


__all__ = ["TerminalApprovalAdapter"]
