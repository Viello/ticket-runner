"""TUI session terminal host launcher and command builder with injection defenses (T059)."""

from __future__ import annotations

from pathlib import Path
import re
from typing import TYPE_CHECKING

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.ports.command_runner import CommandRunner, ProcessHandle

ALLOWED_TERMINAL_HOSTS: tuple[str, ...] = ("wt.exe", "pwsh.exe", "powershell.exe", "cmd.exe")
SESSION_ID_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9_\-]+$")
SHELL_INJECTION_CHARS: tuple[str, ...] = (";", "&", "|", "<", ">", '"', "'", "\n", "\r", "`", "$")


def validate_terminal_host(host: str) -> str:
    """Validate terminal host path against allowed candidate binaries and reject shell metacharacters.

    Args:
        host: Terminal host executable or path (e.g. 'wt.exe', 'C:\\Windows\\System32\\cmd.exe').

    Returns:
        The validated host string.

    Raises:
        ValueError: If host is empty, contains shell injection characters, or is not in ALLOWED_TERMINAL_HOSTS.
    """
    if not isinstance(host, str) or not host.strip():
        raise ValueError("Terminal host must be a non-empty string.")

    cleaned = host.strip()
    for char in SHELL_INJECTION_CHARS:
        if char in cleaned:
            raise ValueError(f"Terminal host contains disallowed shell character: {char!r}")

    basename = Path(cleaned).name.lower()
    if basename not in ALLOWED_TERMINAL_HOSTS:
        allowed_str = ", ".join(ALLOWED_TERMINAL_HOSTS)
        raise ValueError(
            f"Unsupported terminal host '{host}'. Supported terminal hosts are: {allowed_str}"
        )

    return cleaned


def validate_session_id(session_id: str) -> str:
    """Validate OpenCode session identifier strictly against injection and traversal attacks.

    Args:
        session_id: Target session identifier (e.g. 'ses_abc123').

    Returns:
        The validated session ID string.

    Raises:
        ValueError: If session_id is empty, invalid, or contains disallowed characters.
    """
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Session ID must be a non-empty string.")

    cleaned = session_id.strip()
    if not SESSION_ID_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid session ID '{session_id}'. Must be strictly alphanumeric with hyphens or underscores."
        )

    return cleaned


def is_detaching_terminal(host: str) -> bool:
    """Return True if terminal host detaches immediately upon launch (e.g. Windows Terminal wt.exe)."""
    if not isinstance(host, str) or not host.strip():
        return False
    return Path(host.strip()).name.lower() == "wt.exe"


def build_tui_command(host: str, session_id: str) -> list[str]:
    """Construct tokenized exec argument array for launching OpenCode in interactive terminal.

    Args:
        host: Configured terminal host executable or path.
        session_id: Active session identifier to attach to.

    Returns:
        Token list for exec spawn (never raw shell string).

    Raises:
        ValueError: If host or session_id fails security validation.
    """
    valid_host = validate_terminal_host(host)
    valid_session = validate_session_id(session_id)
    basename = Path(valid_host).name.lower()

    if basename == "wt.exe":
        return [valid_host, "opencode", "--session", valid_session]
    elif basename in ("pwsh.exe", "powershell.exe"):
        return [valid_host, "-NoExit", "-Command", "opencode", "--session", valid_session]
    elif basename == "cmd.exe":
        return [valid_host, "/k", "opencode", "--session", valid_session]

    raise ValueError(f"Unsupported terminal host: {valid_host}")


class TuiLauncher:
    """Spawns configured terminal host subprocess attached to OpenCode interactive session."""

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or SubprocessRunner()

    @property
    def command_runner(self) -> CommandRunner:
        """Underlying CommandRunner used to spawn processes."""
        return self._command_runner

    async def launch(
        self,
        host: str,
        session_id: str,
        cwd: Path | None = None,
    ) -> ProcessHandle:
        """Spawn external interactive terminal attached to OpenCode session.

        Args:
            host: Configured terminal host binary name or path.
            session_id: Active OpenCode session ID.
            cwd: Optional working directory.

        Returns:
            ProcessHandle representing the spawned subprocess.
        """
        cmd = build_tui_command(host, session_id)
        return await self._command_runner.spawn(cmd, cwd=cwd)


__all__ = [
    "ALLOWED_TERMINAL_HOSTS",
    "TuiLauncher",
    "build_tui_command",
    "is_detaching_terminal",
    "validate_session_id",
    "validate_terminal_host",
]
