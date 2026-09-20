"""Terminal host auto-detection for TUI session launcher (T061)."""

from __future__ import annotations

import ctypes
from collections.abc import Callable, Mapping
import os
import shutil
import sys

# Windows API constant
MAX_PATH = 260

# Allowed candidate terminal host binaries in fallback priority order
WT_EXE = "wt.exe"
PWSH_EXE = "pwsh.exe"
PSH_EXE = "powershell.exe"
CMD_EXE = "cmd.exe"

ALLOWED_TERMINAL_HOSTS: tuple[str, ...] = (WT_EXE, PWSH_EXE, PSH_EXE, CMD_EXE)

# Environment variable keys
WT_SESSION_ENV = "WT_SESSION"
TERM_PROGRAM_ENV = "TERM_PROGRAM"
VSCODE_PID_ENV = "VSCODE_PID"
PS_MODULE_PATH_ENV = "PSModulePath"
COMSPEC_ENV = "COMSPEC"


def _match_candidate_name(raw_name: str | None) -> str | None:
    """Normalize and match a process or executable name against ALLOWED_TERMINAL_HOSTS.

    Extracts the basename, handles case-insensitivity, ensures .exe suffix,
    and returns the canonical candidate string if it matches ALLOWED_TERMINAL_HOSTS.
    """
    if not raw_name:
        return None
    clean = raw_name.rstrip("\x00").strip()
    if not clean:
        return None
    base = os.path.basename(clean).lower()
    if not base.endswith(".exe"):
        base = f"{base}.exe"
    for candidate in ALLOWED_TERMINAL_HOSTS:
        if base == candidate.lower():
            return candidate
    return None


def _query_process_image_name(pid: int) -> str | None:
    """Query executable image name for a process ID using ctypes QueryFullProcessImageNameW."""
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_process:
            return None
        try:
            buf = ctypes.create_unicode_buffer(MAX_PATH)
            size = ctypes.c_ulong(MAX_PATH)
            if kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
                full_path = buf.value
                return os.path.basename(full_path)
        finally:
            kernel32.CloseHandle(h_process)
    except (OSError, AttributeError, ValueError):
        pass
    return None


def _query_toolhelp_image_name(ppid: int) -> str | None:
    """Fallback: query parent process image name using Windows Toolhelp snapshot API."""
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.windll.kernel32

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_ulong),
                ("cntUsage", ctypes.c_ulong),
                ("th32ProcessID", ctypes.c_ulong),
                ("th32DefaultHeapID", ctypes.c_uintptr),
                ("th32ParentProcessID", ctypes.c_ulong),
                ("cntThreads", ctypes.c_ulong),
                ("th32ModuleID", ctypes.c_ulong),
                ("pcExeFile", ctypes.c_wchar * MAX_PATH),
            ]

        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == ctypes.c_void_p(-1).value or not snapshot:
            return None

        try:
            kernel32.Process32FirstW.restype = ctypes.c_bool
            kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
            kernel32.Process32NextW.restype = ctypes.c_bool
            kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]

            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

            if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                while True:
                    if entry.th32ProcessID == ppid:
                        image = entry.pcExeFile.rstrip("\x00").strip()
                        if image:
                            return os.path.basename(image)
                    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                    if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)
    except (OSError, AttributeError, ValueError):
        pass
    return None


def _default_ppid_resolver() -> str | None:
    """Default resolver that queries the parent process image name via ctypes."""
    try:
        ppid = os.getppid()
        name = _query_process_image_name(ppid)
        if name:
            return name
        return _query_toolhelp_image_name(ppid)
    except Exception:
        return None


class TerminalHostDetector:
    """Auto-detects active caller terminal environment without third-party dependencies."""

    @staticmethod
    def detect(
        env: Mapping[str, str] | None = None,
        path_resolver: Callable[[str], str | None] | None = None,
        ppid_resolver: Callable[[], str | None] | None = None,
    ) -> str | None:
        """Auto-detect active caller terminal environment following sniffing hierarchy.

        Sniffing hierarchy:
        1. WT_SESSION environment variable -> wt.exe.
        2. TERM_PROGRAM=vscode or VSCODE_PID (IDE integrated terminal) ->
           inspect caller shell via ppid_resolver or environment cues (PSModulePath),
           falling back to wt.exe then powershell.exe.
        3. Standalone shell -> inspect parent process via ppid_resolver (ctypes QueryFullProcessImageNameW).
        4. General fallback priority: wt.exe -> pwsh.exe -> powershell.exe -> cmd.exe.

        All returned candidates are verified against path_resolver.

        Args:
            env: Environment variable mapping (defaults to os.environ).
            path_resolver: Resolves binary name to absolute path or None (defaults to shutil.which).
            ppid_resolver: Resolves parent process image name or None (defaults to ctypes inspector).

        Returns:
            Resolved terminal host binary name, or None if no candidate exists on PATH.
        """
        active_env: Mapping[str, str] = os.environ if env is None else env
        resolve_path: Callable[[str], str | None] = (
            shutil.which if path_resolver is None else path_resolver
        )
        resolve_ppid: Callable[[], str | None] = (
            _default_ppid_resolver if ppid_resolver is None else ppid_resolver
        )

        def is_on_path(candidate: str) -> bool:
            return resolve_path(candidate) is not None

        # 1. WT_SESSION environment variable -> wt.exe
        wt_session = active_env.get(WT_SESSION_ENV, "").strip()
        if wt_session and is_on_path(WT_EXE):
            return WT_EXE

        # 2. IDE integrated terminal (TERM_PROGRAM=vscode or VSCODE_PID)
        term_program = active_env.get(TERM_PROGRAM_ENV, "").strip().lower()
        vscode_pid = active_env.get(VSCODE_PID_ENV, "").strip()
        is_ide = term_program == "vscode" or bool(vscode_pid)

        if is_ide:
            # Inspect caller shell via parent process inspection first
            parent_image = resolve_ppid()
            matched_shell = _match_candidate_name(parent_image)
            if matched_shell and is_on_path(matched_shell):
                return matched_shell

            # Inspect environment cues
            if active_env.get(PS_MODULE_PATH_ENV):
                for ps_cand in (PWSH_EXE, PSH_EXE):
                    if is_on_path(ps_cand):
                        return ps_cand

            comspec = active_env.get(COMSPEC_ENV, "").strip()
            if comspec and _match_candidate_name(comspec) == CMD_EXE and is_on_path(CMD_EXE):
                return CMD_EXE

            # IDE fallback: wt.exe then powershell.exe
            if is_on_path(WT_EXE):
                return WT_EXE
            if is_on_path(PSH_EXE):
                return PSH_EXE

        # 3. Standalone shell -> inspect parent process via ppid_resolver
        parent_name = resolve_ppid()
        matched = _match_candidate_name(parent_name)
        if matched and is_on_path(matched):
            return matched

        # 4. General fallback priority: wt.exe -> pwsh.exe -> powershell.exe -> cmd.exe
        for candidate in ALLOWED_TERMINAL_HOSTS:
            if is_on_path(candidate):
                return candidate

        return None


def detect(
    env: Mapping[str, str] | None = None,
    path_resolver: Callable[[str], str | None] | None = None,
    ppid_resolver: Callable[[], str | None] | None = None,
) -> str | None:
    """Module-level helper delegating to TerminalHostDetector.detect."""
    return TerminalHostDetector.detect(
        env=env,
        path_resolver=path_resolver,
        ppid_resolver=ppid_resolver,
    )


__all__ = [
    "ALLOWED_TERMINAL_HOSTS",
    "CMD_EXE",
    "PSH_EXE",
    "PWSH_EXE",
    "TerminalHostDetector",
    "WT_EXE",
    "detect",
]