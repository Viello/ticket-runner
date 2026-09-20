"""Unit tests for TerminalHostDetector (T061)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

import pytest

from runner.adapters.ui.terminal_detector import (
    ALLOWED_TERMINAL_HOSTS,
    CMD_EXE,
    PSH_EXE,
    PWSH_EXE,
    WT_EXE,
    TerminalHostDetector,
    detect,
)


# ---------------------------------------------------------------------------
# Test doubles: path and ppid resolvers
# ---------------------------------------------------------------------------


def _make_path_resolver(*found: str) -> Callable[[str], str | None]:
    """Return a path_resolver that finds the given binaries on PATH."""
    found_set = {f.lower() for f in found}

    def resolver(binary: str) -> str | None:
        if binary.lower() in found_set:
            return f"C:\\Windows\\System32\\{binary}"
        return None

    return resolver


def _make_ppid_resolver(name: str | None = None) -> Callable[[], Optional[str]]:
    """Return a ppid_resolver returning a fixed process image name."""
    return lambda: name


# ---------------------------------------------------------------------------
# 1. WT_SESSION detection branch
# ---------------------------------------------------------------------------


def test_detect_wt_session_success() -> None:
    """WT_SESSION set and wt.exe on PATH -> wt.exe."""
    resolver = _make_path_resolver(WT_EXE)
    env = {"WT_SESSION": "b8f6d7a1-1234-5678-90ab-cdef12345678"}
    ppid_resolver = _make_ppid_resolver()

    result = detect(env, resolver, ppid_resolver)
    assert result == WT_EXE


def test_detect_wt_session_not_on_path_falls_through() -> None:
    """WT_SESSION set but wt.exe missing on PATH -> falls back to next available candidate."""
    resolver = _make_path_resolver(PSH_EXE)
    env = {"WT_SESSION": "some-guid"}
    ppid_resolver = _make_ppid_resolver()

    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


def test_detect_wt_session_empty_string_ignored() -> None:
    """WT_SESSION present but empty string is not treated as Windows Terminal."""
    resolver = _make_path_resolver(WT_EXE, PSH_EXE)
    env = {"WT_SESSION": "   "}
    ppid_resolver = _make_ppid_resolver(PSH_EXE)

    # Should hit standalone shell branch (powershell.exe) rather than wt.exe
    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


# ---------------------------------------------------------------------------
# 2. IDE integrated terminal detection branch
# ---------------------------------------------------------------------------


def test_detect_ide_term_program_vscode_with_caller_powershell() -> None:
    """TERM_PROGRAM=vscode with parent process powershell.exe -> powershell.exe."""
    resolver = _make_path_resolver(WT_EXE, PWSH_EXE, PSH_EXE, CMD_EXE)
    env = {"TERM_PROGRAM": "vscode"}
    ppid_resolver = _make_ppid_resolver("powershell.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


def test_detect_ide_vscode_pid_with_caller_cmd() -> None:
    """VSCODE_PID present with parent process cmd.exe -> cmd.exe."""
    resolver = _make_path_resolver(WT_EXE, PWSH_EXE, PSH_EXE, CMD_EXE)
    env = {"VSCODE_PID": "4892"}
    ppid_resolver = _make_ppid_resolver("cmd.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == CMD_EXE


def test_detect_ide_vscode_with_caller_pwsh() -> None:
    """TERM_PROGRAM=vscode with parent process pwsh.exe -> pwsh.exe."""
    resolver = _make_path_resolver(WT_EXE, PWSH_EXE, PSH_EXE, CMD_EXE)
    env = {"TERM_PROGRAM": "vscode"}
    ppid_resolver = _make_ppid_resolver("pwsh.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PWSH_EXE


def test_detect_ide_vscode_case_insensitive() -> None:
    """TERM_PROGRAM=VSCode is case-insensitively matched."""
    resolver = _make_path_resolver(PSH_EXE)
    env = {"TERM_PROGRAM": "VSCode"}
    ppid_resolver = _make_ppid_resolver("powershell.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


def test_detect_ide_indeterminate_parent_uses_psmodulepath_cue() -> None:
    """IDE shell with unknown parent process infers PowerShell from PSModulePath."""
    resolver = _make_path_resolver(PWSH_EXE, PSH_EXE)
    env = {
        "TERM_PROGRAM": "vscode",
        "PSModulePath": "C:\\Program Files\\PowerShell\\Modules",
    }
    ppid_resolver = _make_ppid_resolver("node.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PWSH_EXE


def test_detect_ide_indeterminate_parent_uses_comspec_cue() -> None:
    """IDE shell with unknown parent process infers cmd.exe from COMSPEC."""
    resolver = _make_path_resolver(CMD_EXE)
    env = {
        "TERM_PROGRAM": "vscode",
        "COMSPEC": "C:\\Windows\\System32\\cmd.exe",
    }
    ppid_resolver = _make_ppid_resolver("electron.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == CMD_EXE


def test_detect_ide_indeterminate_falls_back_to_wt_then_powershell() -> None:
    """IDE shell with no caller shell clues falls back to wt.exe then powershell.exe."""
    # Both wt.exe and powershell.exe available -> picks wt.exe
    resolver_wt = _make_path_resolver(WT_EXE, PSH_EXE, CMD_EXE)
    env = {"TERM_PROGRAM": "vscode"}
    ppid_resolver = _make_ppid_resolver(None)
    assert detect(env, resolver_wt, ppid_resolver) == WT_EXE

    # wt.exe missing -> picks powershell.exe
    resolver_ps = _make_path_resolver(PSH_EXE, CMD_EXE)
    assert detect(env, resolver_ps, ppid_resolver) == PSH_EXE


def test_detect_ide_no_candidate_on_path() -> None:
    """TERM_PROGRAM=vscode but no candidate exists on PATH -> None."""
    resolver = _make_path_resolver()
    env = {"TERM_PROGRAM": "vscode"}
    ppid_resolver = _make_ppid_resolver("cmd.exe")

    assert detect(env, resolver, ppid_resolver) is None


# ---------------------------------------------------------------------------
# 3. Standalone shell parent process inspection
# ---------------------------------------------------------------------------


def test_detect_standalone_parent_powershell() -> None:
    """Standalone shell inspects parent process powershell.exe."""
    resolver = _make_path_resolver(WT_EXE, PSH_EXE, CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver("powershell.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


def test_detect_standalone_parent_pwsh() -> None:
    """Standalone shell inspects parent process pwsh.exe."""
    resolver = _make_path_resolver(WT_EXE, PWSH_EXE, PSH_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver("pwsh.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PWSH_EXE


def test_detect_standalone_parent_cmd() -> None:
    """Standalone shell inspects parent process cmd.exe."""
    resolver = _make_path_resolver(WT_EXE, CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver("cmd.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == CMD_EXE


def test_detect_standalone_parent_full_path_and_casing() -> None:
    """Full path and uppercase image name are normalized correctly."""
    resolver = _make_path_resolver(CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver("C:\\WINDOWS\\SYSTEM32\\CMD.EXE")

    result = detect(env, resolver, ppid_resolver)
    assert result == CMD_EXE


def test_detect_standalone_parent_without_exe_suffix() -> None:
    """Image name without .exe suffix matches candidate."""
    resolver = _make_path_resolver(PSH_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver("powershell")

    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


def test_detect_standalone_matched_parent_not_on_path_falls_through() -> None:
    """Matched parent shell not on PATH falls through to general fallback."""
    # Parent is pwsh.exe, but only powershell.exe is on PATH
    resolver = _make_path_resolver(PSH_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver("pwsh.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


def test_detect_standalone_unrecognized_parent_falls_through() -> None:
    """Unrecognized parent process (e.g. python.exe) falls through to general fallback."""
    resolver = _make_path_resolver(PSH_EXE, CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver("python.exe")

    result = detect(env, resolver, ppid_resolver)
    assert result == PSH_EXE


# ---------------------------------------------------------------------------
# 4. General fallback priority
# ---------------------------------------------------------------------------


def test_detect_fallback_priority_wt_first() -> None:
    """Priority 1: wt.exe."""
    resolver = _make_path_resolver(WT_EXE, PWSH_EXE, PSH_EXE, CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver(None)

    assert detect(env, resolver, ppid_resolver) == WT_EXE


def test_detect_fallback_priority_pwsh_second() -> None:
    """Priority 2: pwsh.exe when wt.exe missing."""
    resolver = _make_path_resolver(PWSH_EXE, PSH_EXE, CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver(None)

    assert detect(env, resolver, ppid_resolver) == PWSH_EXE


def test_detect_fallback_priority_powershell_third() -> None:
    """Priority 3: powershell.exe when wt.exe and pwsh.exe missing."""
    resolver = _make_path_resolver(PSH_EXE, CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver(None)

    assert detect(env, resolver, ppid_resolver) == PSH_EXE


def test_detect_fallback_priority_cmd_fourth() -> None:
    """Priority 4: cmd.exe when only cmd.exe exists."""
    resolver = _make_path_resolver(CMD_EXE)
    env = {}
    ppid_resolver = _make_ppid_resolver(None)

    assert detect(env, resolver, ppid_resolver) == CMD_EXE


def test_detect_no_candidates_returns_none() -> None:
    """Returns None when no candidate terminal hosts exist on PATH."""
    resolver = _make_path_resolver()
    env = {}
    ppid_resolver = _make_ppid_resolver(None)

    assert detect(env, resolver, ppid_resolver) is None


# ---------------------------------------------------------------------------
# 5. Class interface & default parameters
# ---------------------------------------------------------------------------


def test_terminal_host_detector_class_methods() -> None:
    """TerminalHostDetector can be invoked via static or instance method."""
    resolver = _make_path_resolver(WT_EXE)
    env = {"WT_SESSION": "guid"}
    ppid = _make_ppid_resolver()

    detector = TerminalHostDetector()
    assert detector.detect(env, resolver, ppid) == WT_EXE
    assert TerminalHostDetector.detect(env, resolver, ppid) == WT_EXE


def test_detect_default_resolvers_smoke() -> None:
    """Calling detect() without overrides executes safely against active environment."""
    result = detect()
    # In any environment, result must either be a valid allowed candidate or None
    if result is not None:
        assert result in ALLOWED_TERMINAL_HOSTS


def test_allowed_terminal_hosts_tuple() -> None:
    """ALLOWED_TERMINAL_HOSTS defines exactly the candidate priority order."""
    assert ALLOWED_TERMINAL_HOSTS == ("wt.exe", "pwsh.exe", "powershell.exe", "cmd.exe")