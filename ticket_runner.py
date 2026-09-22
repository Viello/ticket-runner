"""Ticket Runner CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
import os
from pathlib import Path
import signal
import sys
from typing import Any, Awaitable, Callable

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.adapters.discord.gateway import DiscordPyGateway
from runner.adapters.discord.smoke import (
    REQUIRED_DISCORD_PERMISSIONS,
    run_smoke,
    verify_channel_permissions,
)
from runner.adapters.filesystem.json_state_store import JsonStateStore
from runner.adapters.ui.keyboard import KeyboardPoller
from runner.adapters.ui.model_prompt import ModelPrompt
from runner.application.crash_recovery import CrashRecoveryCoordinator
from runner.application.doctor import Doctor, DoctorReport
from runner.application.hotkey_dispatch import HotkeyDispatcher
from runner.application.model_selection import ModelSelectionInteractor
from runner.application.presence_coordinator import PresenceCoordinator
from runner.application.queue_orchestrator import QueueOrchestrator
from runner.application.tui_coordinator import TuiCoordinator
from runner.application.worker_supervisor import RunTerminationReason, WorkerSupervisor
from runner.container import BotContainer, RunnerContainer, build_bot_container, build_container
from runner.domain.exceptions import NonInteractiveError, UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.ports.discord_gateway import DiscordGateway
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
        "--live",
        action="store_true",
        help="Perform live gateway connection and channel permission checks for Discord.",
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

    # bot command
    bot_parser = subparsers.add_parser(
        "bot",
        help="Manage standalone Discord bot operations (smoke test or run).",
    )
    bot_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration YAML file (default: config.yaml).",
    )
    bot_group = bot_parser.add_mutually_exclusive_group(required=True)
    bot_group.add_argument(
        "--smoke",
        action="store_true",
        help="Run self-cleaning Discord bot verification sequence.",
    )
    bot_group.add_argument(
        "--run",
        action="store_true",
        help="Start the Discord bot client loop in interactive standalone mode.",
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
    terminal_detector: Any | None = None,
    live: bool = False,
) -> int:
    """Execute Doctor pre-flight checks and display formatted results."""
    pass_mark, fail_mark = _configure_console_encoding()
    print("[Doctor] Verifying environment...")
    doctor = doctor_instance or Doctor(config_path=config_path, terminal_detector=terminal_detector)
    try:
        report: DoctorReport = await doctor.run(local_only=local_only, halt_on_failure=True, live=live)
    except TypeError:
        report = await doctor.run(local_only=local_only, halt_on_failure=True)

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
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    console: Any | None = None,
    keyboard_poller: KeyboardPoller | None = None,
    keyboard_key_reader: Callable[[], str | None] | None = None,
    presence_coordinator: PresenceCoordinator | None = None,
    tui_coordinator: TuiCoordinator | None = None,
    terminal_detector: Any | None = None,
) -> int:
    """Execute Doctor pre-flight checks, validate configuration, and drive queue lifecycle."""
    _configure_console_encoding()
    doctor = doctor_instance or Doctor(config_path=config_path, terminal_detector=terminal_detector)
    doctor_code = await run_doctor(
        config_path=config_path,
        local_only=local_only,
        doctor_instance=doctor,
        terminal_detector=terminal_detector,
    )
    if doctor_code != 0:
        return doctor_code

    config = doctor.loaded_config
    if config is None:
        loader = YamlConfigLoader()
        config = loader.load(config_path)

    supervisor: WorkerSupervisor | None = supervisor_instance
    crash_recovery: CrashRecoveryCoordinator | None = crash_recovery_instance
    state_coordinator = None
    terminal_display = None
    ui_event_sink = None
    tui_coord: TuiCoordinator | None = tui_coordinator
    if container_instance is not None:
        orchestrator = container_instance.orchestrator
        if supervisor is None:
            supervisor = getattr(container_instance, "supervisor", None)
        if crash_recovery is None:
            crash_recovery = getattr(container_instance, "crash_recovery", None)
        state_coordinator = getattr(container_instance, "state_coordinator", None)
        terminal_display = getattr(container_instance, "terminal_display", None)
        ui_event_sink = getattr(container_instance, "ui_event_sink", None)
        if presence_coordinator is None:
            presence_coordinator = getattr(container_instance, "presence_coordinator", None)
        if tui_coord is None:
            tui_coord = getattr(container_instance, "tui_coordinator", None)
    elif orchestrator_instance is not None:
        orchestrator = orchestrator_instance
        if supervisor is None:
            supervisor = getattr(orchestrator, "supervisor", None)
        if crash_recovery is None:
            crash_recovery = getattr(orchestrator, "crash_recovery", None)
        state_coordinator = getattr(orchestrator, "state_coordinator", None)
        terminal_display = getattr(orchestrator, "terminal_display", None)
        ui_event_sink = getattr(orchestrator, "ui_event_sink", None)
        if tui_coord is None:
            tui_coord = getattr(orchestrator, "tui_coordinator", None)
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
            console=console,
            terminal_detector=terminal_detector,
        )
        orchestrator = getattr(container, "orchestrator", None)
        if supervisor is None:
            supervisor = getattr(container, "supervisor", None)
        if crash_recovery is None:
            crash_recovery = getattr(container, "crash_recovery", None)
        state_coordinator = getattr(container, "state_coordinator", None)
        terminal_display = getattr(container, "terminal_display", None)
        ui_event_sink = getattr(container, "ui_event_sink", None)
        if presence_coordinator is None:
            presence_coordinator = getattr(container, "presence_coordinator", None)
        if tui_coord is None:
            tui_coord = getattr(container, "tui_coordinator", None)

    resolved_presence = presence_coordinator or PresenceCoordinator(
        state_coordinator=state_coordinator,
        terminal_display=terminal_display,
        ui_event_sink=ui_event_sink,
    )

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

    hotkey_dispatcher = HotkeyDispatcher(
        orchestrator=orchestrator,
        presence_coordinator=resolved_presence,
        supervisor=supervisor,
        stop_event=stop_event,
        state_coordinator=state_coordinator,
        ui_event_sink=ui_event_sink,
        terminal_display=terminal_display,
        on_shutdown=_trigger_graceful_stop,
        tui_coordinator=tui_coord,
    )

    poller = keyboard_poller or KeyboardPoller(
        key_reader=keyboard_key_reader,
        on_key=hotkey_dispatcher,
    )
    poller.start()

    active_display = (
        terminal_display
        or getattr(container_instance, "terminal_display", None)
        or getattr(orchestrator_instance, "terminal_display", None)
    )
    if active_display is not None and hasattr(active_display, "start"):
        active_display.start()

    draining = False
    try:
        if crash_recovery is not None:
            try:
                await crash_recovery.recover()
            except Exception as exc:
                print(f"\n[Runner] Error during crash recovery: {exc}")

        if shutting_down:
            return 130

        exit_code = await orchestrator.run_lifecycle(
            lifecycle=config.lifecycle,
            poll_interval=effective_poll_interval,
            stop_event=stop_event,
            clock=clock,
            sleep_fn=sleep_fn,
            console=console,
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
        if active_display is not None and hasattr(active_display, "stop"):
            active_display.stop()
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
        await poller.stop()
        if active_display is not None and hasattr(active_display, "stop"):
            active_display.stop()
        if old_sigint is not None:
            try:
                signal.signal(signal.SIGINT, old_sigint)
            except (ValueError, AttributeError):
                pass
        if hasattr(orchestrator, "release_lock"):
            orchestrator.release_lock()


async def run_bot(
    config_path: Path | None = None,
    smoke: bool = False,
    run: bool = False,
    container_instance: BotContainer | None = None,
    gateway: DiscordGateway | None = None,
    permission_checker: Callable[[Any, Any], Awaitable[list[str]]] | None = None,
    stderr: Any | None = None,
    stop_event: asyncio.Event | None = None,
) -> int:
    """Execute standalone Discord bot subcommand (--smoke or --run)."""
    err_stream = stderr or sys.stderr
    container = container_instance or build_bot_container(config_path=config_path)
    config = container.config

    if not config.discord.enabled:
        err_stream.write("Error: Discord is disabled in configuration (discord.enabled is false).\n")
        return 1

    if not config.discord.channel_id:
        err_stream.write("Error: Missing discord.channel_id in configuration.\n")
        return 1

    token_env = config.discord.token_env
    token_val = os.environ.get(token_env, "").strip()
    if not token_val:
        err_stream.write(
            f"Authentication failed: Missing or empty bot token in environment variable '{token_env}'.\n"
        )
        return 1

    client = container.discord_client

    if smoke:
        start_task = asyncio.create_task(client.start())
        ready_task = asyncio.create_task(client.ready_event.wait())
        try:
            done, pending = await asyncio.wait(
                [start_task, ready_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=30.0,
            )
            if ready_task not in done:
                if start_task in done:
                    exc = start_task.exception()
                    err_stream.write(f"Authentication failed: {exc}\n")
                else:
                    err_stream.write("Authentication failed: Connection timed out connecting to Discord.\n")
                for p in pending:
                    p.cancel()
                await client.close()
                return 1

            if getattr(client, "ready_error", None) is not None:
                err_stream.write(f"Discord connection error: {client.ready_error}\n")
                for p in pending:
                    p.cancel()
                await client.close()
                return 1
        except Exception as exc:
            err_stream.write(f"Authentication failed: {exc}\n")
            await client.close()
            return 1

        channel_id = config.discord.channel_id
        channel: Any = None
        try:
            chan_int = int(channel_id)
            if hasattr(client.client, "get_channel"):
                channel = client.client.get_channel(chan_int)
            if channel is None and hasattr(client.client, "fetch_channel"):
                channel = await client.client.fetch_channel(chan_int)
        except Exception as exc:
            err_stream.write(f"Failed to fetch channel {channel_id}: {exc}\n")
            await client.close()
            if not start_task.done():
                start_task.cancel()
            return 1

        if channel is None:
            err_stream.write(f"Channel {channel_id} not found.\n")
            await client.close()
            if not start_task.done():
                start_task.cancel()
            return 1

        try:
            if permission_checker is not None:
                missing = await permission_checker(channel, client.client)
            else:
                missing = await verify_channel_permissions(channel, client.client)
        except Exception as exc:
            err_stream.write(f"Permission verification failed: {exc}\n")
            await client.close()
            if not start_task.done():
                start_task.cancel()
            return 1

        if missing:
            err_stream.write(
                f"Missing required permission(s): {', '.join(missing)}\n"
            )
            await client.close()
            if not start_task.done():
                start_task.cancel()
            return 1

        try:
            gw = gateway or DiscordPyGateway(client.client)
            await run_smoke(gw, channel_id)
        except Exception as exc:
            err_stream.write(f"Smoke test failed: {exc}\n")
            await client.close()
            if not start_task.done():
                start_task.cancel()
            return 1

        await client.close()
        if not start_task.done():
            start_task.cancel()
            try:
                await start_task
            except (asyncio.CancelledError, Exception):
                pass
        return 0

    if run:
        loop = asyncio.get_running_loop()
        effective_stop_event = stop_event or asyncio.Event()

        def _sigint_handler(signum: int, frame: Any) -> None:
            loop.call_soon_threadsafe(effective_stop_event.set)

        old_sigint = None
        try:
            old_sigint = signal.signal(signal.SIGINT, _sigint_handler)
        except (ValueError, AttributeError):
            pass

        start_task = asyncio.create_task(client.start())
        try:
            ready_task = asyncio.create_task(client.ready_event.wait())
            wait_task = asyncio.create_task(effective_stop_event.wait())
            done, pending = await asyncio.wait(
                [start_task, ready_task, wait_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if effective_stop_event.is_set():
                return 130
            if start_task in done:
                exc = start_task.exception()
                if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                    return 130
                if exc is not None:
                    err_stream.write(f"Bot error: {exc}\n")
                    return 1
            if getattr(client, "ready_error", None) is not None:
                err_stream.write(f"Discord connection error: {client.ready_error}\n")
                return 1
            if ready_task in done and not effective_stop_event.is_set():
                print("[Bot] Connected to Discord and slash commands synced. Ready.")
                done2, pending2 = await asyncio.wait(
                    [start_task, wait_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if effective_stop_event.is_set():
                    return 130
                if start_task in done2:
                    exc = start_task.exception()
                    if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                        return 130
                    if exc is not None:
                        err_stream.write(f"Bot error: {exc}\n")
                        return 1
            return 0
        except KeyboardInterrupt:
            return 130
        finally:
            await client.close()
            if not start_task.done():
                start_task.cancel()
                try:
                    await start_task
                except (asyncio.CancelledError, Exception):
                    pass
            if old_sigint is not None:
                try:
                    signal.signal(signal.SIGINT, old_sigint)
                except (ValueError, AttributeError):
                    pass

    return 0




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
            return asyncio.run(
                run_doctor(
                    config_path=config_path,
                    local_only=local_only,
                    live=getattr(args, "live", False),
                )
            )
        elif args.command == "start":
            return asyncio.run(
                run_start(
                    config_path=config_path,
                    local_only=local_only,
                    model_id=getattr(args, "model", None),
                )
            )
        elif args.command == "bot":
            return asyncio.run(
                run_bot(
                    config_path=config_path,
                    smoke=getattr(args, "smoke", False),
                    run=getattr(args, "run", False),
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
