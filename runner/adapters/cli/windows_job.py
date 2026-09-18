"""Windows Job Object integration for robust child process and tree reaping."""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# Win32 Constants
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: int = 0x2000
JobObjectExtendedLimitInformation: int = 9
PROCESS_SET_QUOTA: int = 0x0100
PROCESS_TERMINATE: int = 0x0001


if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.wintypes.DWORD),
            ("SchedulingClass", ctypes.wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]
else:
    ctypes = None  # type: ignore[assignment]
    ctypes_wintypes = None


class WindowsJobObject:
    """Manages a Windows Job Object handle configured with KILL_ON_JOB_CLOSE."""

    def __init__(self, handle: int | None = None) -> None:
        self._handle = handle

    @property
    def handle(self) -> int | None:
        """Raw Win32 OS handle, or None if closed/unassigned."""
        return self._handle

    @property
    def is_open(self) -> bool:
        """Whether the Job Object handle is currently open and valid."""
        return self._handle is not None

    @classmethod
    def create(cls) -> WindowsJobObject | None:
        """Create and configure a new Windows Job Object with KILL_ON_JOB_CLOSE.

        Returns:
            An active WindowsJobObject instance on Windows, or None on non-Windows or if creation fails.
        """
        if sys.platform != "win32":
            return None

        try:
            kernel32 = ctypes.windll.kernel32
            h_job = kernel32.CreateJobObjectW(None, None)
            if not h_job:
                logger.warning("Failed to create Windows Job Object: CreateJobObjectW returned NULL")
                return None

            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            success = kernel32.SetInformationJobObject(
                h_job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not success:
                logger.warning("Failed to configure Job Object limits: SetInformationJobObject returned 0")
                kernel32.CloseHandle(h_job)
                return None

            return cls(h_job)
        except Exception as exc:
            logger.warning(f"Exception creating Windows Job Object: {exc}")
            return None

    def assign_process(self, pid_or_proc: int | Any) -> bool:
        """Assign a process to this Job Object.

        Args:
            pid_or_proc: Process PID integer or an object exposing a .pid property.

        Returns:
            True if assignment succeeded, False otherwise.
        """
        if self._handle is None or sys.platform != "win32":
            return False

        pid = getattr(pid_or_proc, "pid", pid_or_proc)
        if not isinstance(pid, int) or pid <= 0:
            return False

        try:
            kernel32 = ctypes.windll.kernel32
            h_proc = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
            if not h_proc:
                logger.warning(f"Could not open process {pid} for Job Object assignment")
                return False

            try:
                assigned = kernel32.AssignProcessToJobObject(self._handle, h_proc)
                return bool(assigned)
            finally:
                kernel32.CloseHandle(h_proc)
        except Exception as exc:
            logger.warning(f"Failed to assign process {pid} to Job Object: {exc}")
            return False

    def terminate(self, exit_code: int = 1) -> bool:
        """Terminate all processes in the Job Object immediately and close the handle.

        Args:
            exit_code: Non-zero exit code to report for terminated processes.

        Returns:
            True if termination was requested, False if handle was already closed.
        """
        if self._handle is None or sys.platform != "win32":
            return False

        try:
            kernel32 = ctypes.windll.kernel32
            res = kernel32.TerminateJobObject(self._handle, exit_code)
            return bool(res)
        except Exception as exc:
            logger.warning(f"Failed to terminate Job Object processes: {exc}")
            return False
        finally:
            self.close()

    def close(self) -> None:
        """Idempotently close the Windows Job Object handle.

        When closed, any remaining processes in the job will be reaped by the OS
        due to JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        """
        if self._handle is not None and sys.platform == "win32":
            h = self._handle
            self._handle = None
            try:
                ctypes.windll.kernel32.CloseHandle(h)
            except Exception as exc:
                logger.warning(f"Exception closing Job Object handle: {exc}")
        self._handle = None

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> WindowsJobObject:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
