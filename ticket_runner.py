"""Ticket Runner CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path
import sys

from runner.application.doctor import Doctor, DoctorReport


def create_parser() -> argparse.ArgumentParser:
    """Create top-level ArgumentParser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="ticket_runner",
        description="Ticket Runner: Local orchestrator for autonomous ticket execution.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Bypass Discord bot verification and notifications (terminal-only mode).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration YAML file (default: config.yaml).",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # doctor command
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run pre-flight environment checks to verify system prerequisites.",
    )
    doctor_parser.add_argument(
        "--local-only",
        action="store_true",
        help="Bypass Discord bot verification and notifications.",
    )
    doctor_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration YAML file (default: config.yaml).",
    )

    # placeholders for future subcommands
    subparsers.add_parser("start", help="Start the ticket queue execution (Spec 02+).")
    subparsers.add_parser("pause", help="Pause the active ticket execution.")
    subparsers.add_parser("status", help="Display current runner and ticket status.")

    return parser


def _configure_console_encoding() -> tuple[str, str]:
    """Configure stdout for utf-8 if supported, and return display marks."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    pass_mark = "✓"
    fail_mark = "✗"
    try:
        pass_mark.encode(sys.stdout.encoding or "utf-8")
    except UnicodeEncodeError:
        pass_mark = "[PASS]"
        fail_mark = "[FAIL]"

    return pass_mark, fail_mark


async def run_doctor(
    config_path: Path,
    local_only: bool,
    doctor_instance: Doctor | None = None,
) -> int:
    """Execute Doctor pre-flight checks and display formatted results."""
    pass_mark, fail_mark = _configure_console_encoding()
    print("[Doctor] Verifying environment...")
    doctor = doctor_instance or Doctor(config_path=config_path)
    report: DoctorReport = await doctor.run(local_only=local_only, halt_on_failure=True)

    for check in report.checks:
        if check.passed:
            print(f"  {pass_mark} {check.message}")
        else:
            print(f"  {fail_mark} {check.message}")
            if check.remediation:
                print(f"    Remediation: {check.remediation}")

    if report.passed:
        print("\nPre-flight verification passed.")
        return 0
    else:
        print("\nDoctor pre-flight verification failed.")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point returning status exit code."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    local_only = getattr(args, "local_only", False)
    config_path = getattr(args, "config", Path("config.yaml"))

    if args.command == "doctor":
        return asyncio.run(run_doctor(config_path=config_path, local_only=local_only))
    elif args.command in ("start", "pause", "status"):
        print(f"Command '{args.command}' is not yet implemented (scheduled in upcoming specs).")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
