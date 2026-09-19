"""Ticket Runner CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path
import signal
import sys
from typing import Any

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.adapters.filesystem.json_state_store import JsonStateStore
from runner.adapters.ui.model_prompt import ModelPrompt
from runner.application.crash_recovery import CrashRecoveryCoordinator
from runner.application.doctor import Doctor, DoctorReport
from runner.application.model_selection import ModelSelectionInteractor
from runner.application.queue_orchestrator import QueueOrchestrator
from runner.application.worker_supervisor import RunTerminationReason, WorkerSupervisor
from runner.container import RunnerContainer, build_container
from runner.domain.exceptions import NonInteractiveError, UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.ports.state_store import StateStore


EXIT_CODE_CONTRACT = """Exit codes:
  0    Clean termination (queue drained under terminate policy, or standby exited via stop)
  1    Runtime error
  2    Operator abort (UserAbortError)
  130  Graceful SIGINT (single or forced second press)
"""


def create_parser() -> argparse.ArgumentParser:
    """Create top-level ArgumentParser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="ticket_runner",
        description="Ticket Runner: Local orchestrator for autonomous ticket execution.",
        epilog=EXIT_CODE_CONTRACT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    # start command
    start_parser = subparsers.add_parser(
        "start",
        help="Start the ticket queue execution (Spec 02+).",
        epilog=EXIT_CODE_CONTRACT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    start_parser.add_argument(
        "--local-only",
        action="store_true",
        help="Bypass Discord bot verification and notifications.",
    )
    start_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration YAML file (default: config.yaml).",
    )
    start_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="OpenCode model identifier to use for session runs.",
    )

    # placeholders for future subcommands
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


async def run_start(
    config_path: Path,
    local_only: bool,
    doctor_instance: Doctor | None = None,
    orchestrator_instance: QueueOrchestrator | None = None,
    poll_interval: float | None = None,
    container_instance: RunnerContainer | None = None,
    stop_event: asyncio.Event | None = None,
    supervisor_instance: WorkerSupervisor | None = None,
    clock: Callable[[], float] | None = None,
    model_id: str | None = None,
    state_store: StateStore | None = None,
    model_prompt: ModelPrompt | None = None,
    key_reader: Callable[[], str] | None = None,
    crash_recovery_instance: CrashRecoveryCoordinator | None = None,
) -> int:
    """Execute Doctor pre-flight checks, validate configuration, and drive queue lifecycle."""
    doctor = doctor_instance or Doctor(config_path=config_path)
    doctor_code = await run_doctor(
        config_path=config_path,
        local_only=local_only,
        doctor_instance=doctor,
    )
    if doctor_code != 0:
        return doctor_code

    config = doctor.loaded_config
    if config is None:
        loader = YamlConfigLoader()
        config = loader.load(config_path)

    supervisor: WorkerSupervisor | None = supervisor_instance
    crash_recovery: CrashRecoveryCoordinator | None = crash_recovery_instance
    if container_instance is not None:
        orchestrator = container_instance.orchestrator
        if supervisor is None:
            supervisor = container_instance.supervisor
        if crash_recovery is None:
            crash_recovery = getattr(container_instance, "crash_recovery", None)
    elif orchestrator_instance is not None:
        orchestrator = orchestrator_instance
        if supervisor is None:
            supervisor = getattr(orchestrator, "supervisor", None)
        if crash_recovery is None:
            crash_recovery = getattr(orchestrator, "crash_recovery", None)
    else:
        if model_id is not None:
            valid_model_ids = [m.id for m in config.model.models]
            if model_id not in valid_model_ids:
                configured_ids_str = ", ".join(valid_model_ids) if valid_model_ids else "none"
                print(
                    f"\n[Runner] Error: Unknown model '{model_id}'. "
                    f"Configured model IDs: {configured_ids_str}"
                )
                return 1

        effective_state_store = state_store
        if effective_state_store is None:
            runtime_paths = RuntimePaths()
            effective_state_store = JsonStateStore(path=runtime_paths.state_path)

        prompt_adapter = model_prompt or ModelPrompt(read_key=key_reader)
        interactor = ModelSelectionInteractor(
            config=config,
            state_store=effective_state_store,
            prompt=prompt_adapter,
        )

        try:
            model_id = interactor.resolve_and_persist(cli_model=model_id)
        except NonInteractiveError as exc:
            print(f"\n[Runner] Error: {exc}")
            return 1
        except Exception as exc:
            print(f"\n[Runner] Error: State persistence failed: {exc}")
            return 1

        container = build_container(
            config=config,
            clock=clock,
            model_id=model_id,
            state_store=effective_state_store,
        )
        orchestrator = container.orchestrator
        if supervisor is None:
            supervisor = container.supervisor
        if crash_recovery is None:
            crash_recovery = getattr(container, "crash_recovery", None)

    if crash_recovery is not None:
        try:
            await crash_recovery.recover()
        except Exception as exc:
            print(f"\n[Runner] Error during crash recovery: {exc}")

    if stop_event is None:
        stop_event = asyncio.Event()

    effective_poll_interval = (
        poll_interval if poll_interval is not None else config.lifecycle.poll_interval
    )

    loop = asyncio.get_running_loop()
    shutting_down = False

    def _trigger_graceful_stop() -> None:
        nonlocal shutting_down
        shutting_down = True
        if stop_event is not None and not stop_event.is_set():
            stop_event.set()
        active_supervisor = supervisor or getattr(orchestrator, "supervisor", None)
        if active_supervisor is not None:
            active_supervisor.request_kill(RunTerminationReason.KILLED_INTERRUPT)

    def _sigint_handler(signum: int, frame: Any) -> None:
        nonlocal shutting_down
        if shutting_down:
            sys.exit(130)
        shutting_down = True
        try:
            loop.call_soon_threadsafe(_trigger_graceful_stop)
        except RuntimeError:
            pass

    old_sigint = None
    try:
        old_sigint = signal.signal(signal.SIGINT, _sigint_handler)
    except (ValueError, AttributeError):
        pass

    draining = False
    try:
        exit_code = await orchestrator.run_lifecycle(
            lifecycle=config.lifecycle,
            poll_interval=effective_poll_interval,
            stop_event=stop_event,
            clock=clock,
        )
        if shutting_down:
            return 130
        return exit_code
    except KeyboardInterrupt:
        if draining:
            sys.exit(130)
        draining = True
        shutting_down = True
        _trigger_graceful_stop()
        active_supervisor = supervisor or getattr(orchestrator, "supervisor", None)
        if (
            active_supervisor is not None
            and getattr(active_supervisor, "_current_handle", None) is not None
        ):
            try:
                handle = active_supervisor._current_handle
                if handle is not None:
                    await active_supervisor._terminate_ladder(handle)
            except Exception:
                pass
        if hasattr(orchestrator, "print_completion_summary"):
            try:
                await orchestrator.print_completion_summary()
            except Exception:
                pass
        if hasattr(orchestrator, "release_lock"):
            orchestrator.release_lock()
        return 130
    except UserAbortError as exc:
        if shutting_down:
            return 130
        print(f"\n[Runner] Aborted: {exc}")
        return 2
    except RuntimeError as exc:
        if shutting_down:
            return 130
        print(f"\n[Runner] Error: {exc}")
        return 1
    finally:
        if old_sigint is not None:
            try:
                signal.signal(signal.SIGINT, old_sigint)
            except (ValueError, AttributeError):
                pass
        if hasattr(orchestrator, "release_lock"):
            orchestrator.release_lock()


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point returning status exit code."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    local_only = getattr(args, "local_only", False)
    config_path = getattr(args, "config", Path("config.yaml"))

    try:
        if args.command == "doctor":
            return asyncio.run(run_doctor(config_path=config_path, local_only=local_only))
        elif args.command == "start":
            return asyncio.run(
                run_start(
                    config_path=config_path,
                    local_only=local_only,
                    model_id=getattr(args, "model", None),
                )
            )
        elif args.command in ("pause", "status"):
            print(f"Command '{args.command}' is not yet implemented (scheduled in upcoming specs).")
            return 0
    except KeyboardInterrupt:
        return 130

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
