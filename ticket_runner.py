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

from runner.adapters.cli.scaffolder import ProjectScaffolder
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
from runner.application.prompt_generator import AIPromptGenerator
from runner.application.queue_orchestrator import QueueOrchestrator
from runner.application.scaffolding import ProjectSniffer
from runner.application.tui_coordinator import TuiCoordinator
from runner.application.worker_supervisor import RunTerminationReason, WorkerSupervisor
from runner.container import BotContainer, RunnerContainer, build_bot_container, build_container
from runner.domain.exceptions import NonInteractiveError, UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.ports.discord_gateway import DiscordGateway
from runner.ports.skills_client import SkillsClient
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
        "--project-dir",
        type=Path,
        default=Path.cwd().resolve(),
        help="Target project directory path (default: current directory).",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Bypass Discord bot verification and notifications (terminal-only mode).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to configuration YAML file (default: ticket-runner.yaml or config.yaml).",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # init command
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize and scaffold Ticket Runner in a target project.",
    )
    init_parser.add_argument(
        "--project-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Target project directory path (default: current directory).",
    )
    init_parser.add_argument(
        "--ai-prompt",
        action="store_true",
        help="Print the generated Markdown prompt for AI assistants to stdout and exit 0 immediately.",
    )
    init_parser.add_argument(
        "--yes",
        "--non-interactive",
        dest="non_interactive",
        action="store_true",
        help="Automatically accept detected defaults without prompting.",
    )
    init_parser.add_argument(
        "--no-skills",
        action="store_true",
        help="Bypass skills synchronization during scaffolding.",
    )

    # skills command
    skills_parser = subparsers.add_parser(
        "skills",
        help="Manage Ticket Runner skills catalog.",
    )
    skills_subparsers = skills_parser.add_subparsers(
        dest="skills_action",
        help="Skills action to execute",
    )
    skills_sync_parser = skills_subparsers.add_parser(
        "sync",
        help="Synchronize skills catalog into target project.",
    )
    skills_sync_parser.add_argument(
        "--project-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Target project directory path (default: current directory).",
    )
    skills_sync_parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing skills even if local modifications exist.",
    )

    # doctor command
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run pre-flight environment checks to verify system prerequisites.",
    )
    doctor_parser.add_argument(
        "--project-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Target project directory path (default: current directory).",
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
        default=argparse.SUPPRESS,
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
        "--project-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Target project directory path (default: current directory).",
    )
    start_parser.add_argument(
        "--local-only",
        action="store_true",
        help="Bypass Discord bot verification and notifications.",
    )
    start_parser.add_argument(
        "--config",
        type=Path,
        default=argparse.SUPPRESS,
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
        "--project-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Target project directory path (default: current directory).",
    )
    bot_parser.add_argument(
        "--config",
        type=Path,
        default=argparse.SUPPRESS,
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

    # notify command
    notify_parser = subparsers.add_parser(
        "notify",
        help="Post a single notification message to the configured Discord channel and exit.",
    )
    notify_parser.add_argument(
        "message",
        type=str,
        help="Notification message to post to Discord status channel.",
    )
    notify_parser.add_argument(
        "--project-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Target project directory path (default: current directory).",
    )
    notify_parser.add_argument(
        "--config",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to configuration YAML file (default: config.yaml).",
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
    config_path: Path | None = None,
    local_only: bool = False,
    doctor_instance: Doctor | None = None,
    terminal_detector: Any | None = None,
    live: bool = False,
    project_dir: Path | None = None,
) -> int:
    """Execute Doctor pre-flight checks and display formatted results."""
    resolved_project_dir: Path | None = None
    if project_dir is not None:
        resolved_project_dir = Path(project_dir).resolve()
        if not resolved_project_dir.exists():
            print(f"\n[Runner] Error: Project directory '{resolved_project_dir}' does not exist.")
            return 1
        if not resolved_project_dir.is_dir():
            print(f"\n[Runner] Error: Project path '{resolved_project_dir}' is not a directory.")
            return 1

    pass_mark, fail_mark = _configure_console_encoding()
    print("[Doctor] Verifying environment...")

    doctor = doctor_instance or Doctor(
        config_path=config_path,
        terminal_detector=terminal_detector,
        cwd=resolved_project_dir,
        project_dir=resolved_project_dir,
    )
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
    config_path: Path | None = None,
    local_only: bool = False,
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
    project_dir: Path | None = None,
) -> int:
    """Execute Doctor pre-flight checks, validate configuration, and drive queue lifecycle."""
    resolved_project_dir: Path | None = None
    if project_dir is not None:
        resolved_project_dir = Path(project_dir).resolve()
        if not resolved_project_dir.exists():
            print(f"\n[Runner] Error: Project directory '{resolved_project_dir}' does not exist.")
            return 1
        if not resolved_project_dir.is_dir():
            print(f"\n[Runner] Error: Project path '{resolved_project_dir}' is not a directory.")
            return 1

    _configure_console_encoding()
    doctor = doctor_instance or Doctor(
        config_path=config_path,
        terminal_detector=terminal_detector,
        cwd=resolved_project_dir,
        project_dir=resolved_project_dir,
    )
    doctor_code = await run_doctor(
        config_path=config_path,
        local_only=local_only,
        doctor_instance=doctor,
        terminal_detector=terminal_detector,
        project_dir=resolved_project_dir,
    )
    if doctor_code != 0:
        return doctor_code

    config = doctor.loaded_config
    if config is None:
        loader = YamlConfigLoader()
        effective_project_dir = resolved_project_dir or Path.cwd().resolve()
        explicit_overlay = (
            config_path
            if config_path is not None and getattr(doctor, "_config_path_explicit", False)
            else None
        )
        config = loader.load_two_tier(
            project_dir=effective_project_dir,
            project_config_path=explicit_overlay,
        )

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
            runtime_paths = (
                RuntimePaths(root_dir=resolved_project_dir / ".agent")
                if resolved_project_dir
                else RuntimePaths()
            )
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
            project_dir=resolved_project_dir,
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

    idle_esc_min = getattr(getattr(config, "presence", None), "idle_escalation_minutes", 3)
    resolved_presence = presence_coordinator or PresenceCoordinator(
        state_coordinator=state_coordinator,
        terminal_display=terminal_display,
        ui_event_sink=ui_event_sink,
        idle_escalation_minutes=idle_esc_min,
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
    project_dir: Path | None = None,
) -> int:
    """Execute standalone Discord bot subcommand (--smoke or --run)."""
    err_stream = stderr or sys.stderr
    resolved_project_dir: Path | None = None
    if project_dir is not None:
        resolved_project_dir = Path(project_dir).resolve()
        if not resolved_project_dir.exists():
            err_stream.write(f"\n[Runner] Error: Project directory '{resolved_project_dir}' does not exist.\n")
            return 1
        if not resolved_project_dir.is_dir():
            err_stream.write(f"\n[Runner] Error: Project path '{resolved_project_dir}' is not a directory.\n")
            return 1

    effective_config_path = config_path
    if resolved_project_dir is not None and config_path is not None and not config_path.is_absolute():
        effective_config_path = resolved_project_dir / config_path

    container = container_instance or build_bot_container(
        config_path=effective_config_path,
        project_dir=resolved_project_dir,
    )
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


async def run_notify(
    message: str,
    config_path: Path | None = None,
    container_instance: BotContainer | None = None,
    gateway: DiscordGateway | None = None,
    stderr: Any | None = None,
    project_dir: Path | None = None,
) -> int:
    """Execute one-shot Discord notification and exit (T114, Spec 14)."""
    err_stream = stderr or sys.stderr

    if not message or not message.strip():
        err_stream.write("Error: Notification message cannot be empty.\n")
        return 1

    resolved_project_dir: Path | None = None
    if project_dir is not None:
        resolved_project_dir = Path(project_dir).resolve()
        if not resolved_project_dir.exists():
            err_stream.write(f"\n[Runner] Error: Project directory '{resolved_project_dir}' does not exist.\n")
            return 1
        if not resolved_project_dir.is_dir():
            err_stream.write(f"\n[Runner] Error: Project path '{resolved_project_dir}' is not a directory.\n")
            return 1

    effective_config_path = config_path
    if resolved_project_dir is not None and config_path is not None and not config_path.is_absolute():
        effective_config_path = resolved_project_dir / config_path

    try:
        container = container_instance or build_bot_container(
            config_path=effective_config_path,
            project_dir=resolved_project_dir,
        )
    except Exception as exc:
        err_stream.write(f"Configuration error: {exc}\n")
        return 1

    config = container.config

    if not config.discord.enabled:
        err_stream.write("Error: Discord is disabled in configuration (discord.enabled is false).\n")
        return 1

    if not config.discord.channel_id:
        err_stream.write("Error: Missing discord.channel_id in configuration.\n")
        return 1

    if not config.discord.channel_id.strip().isdigit():
        err_stream.write(
            f"Error: Invalid discord.channel_id '{config.discord.channel_id}' in configuration (must be numeric snowflake).\n"
        )
        return 1

    token_env = config.discord.token_env
    token_val = os.environ.get(token_env, "").strip()
    if not token_val:
        err_stream.write(
            f"Authentication failed: Missing or empty bot token in environment variable '{token_env}'.\n"
        )
        return 1

    def _sanitize(text: str) -> str:
        if token_val and token_val in text:
            return text.replace(token_val, "[REDACTED]")
        return text

    gw = gateway
    if gw is not None:
        try:
            await gw.post_message(config.discord.channel_id, message)
            return 0
        except Exception as exc:
            err_stream.write(f"Error posting notification: {_sanitize(str(exc))}\n")
            return 1

    # Live gateway execution using container client
    client = container.discord_client
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
                err_stream.write(f"Authentication failed: {_sanitize(str(exc))}\n")
            else:
                err_stream.write("Authentication failed: Connection timed out connecting to Discord.\n")
            for p in pending:
                p.cancel()
            await client.close()
            return 1

        if getattr(client, "ready_error", None) is not None:
            err_stream.write(f"Discord connection error: {_sanitize(str(client.ready_error))}\n")
            for p in pending:
                p.cancel()
            await client.close()
            return 1

        live_gw = DiscordPyGateway(client.client)
        await live_gw.post_message(config.discord.channel_id, message)
        return 0
    except Exception as exc:
        err_stream.write(f"Error posting notification: {_sanitize(str(exc))}\n")
        return 1
    finally:
        await client.close()
        if not start_task.done():
            start_task.cancel()
            try:
                await start_task
            except (asyncio.CancelledError, Exception):
                pass




def run_init(
    project_dir: Path,
    ai_prompt: bool = False,
    non_interactive: bool = False,
    no_skills: bool = False,
    scaffolder: ProjectScaffolder | None = None,
    sniffer: ProjectSniffer | None = None,
) -> int:
    """Scaffold target project directory structure or output AI prompt."""
    resolved_dir = Path(project_dir).resolve()
    if ai_prompt:
        sn = sniffer or ProjectSniffer()
        try:
            heuristics = sn.sniff(resolved_dir)
        except Exception:
            heuristics = None
        prompt = AIPromptGenerator.generate(heuristics)
        print(prompt)
        return 0

    scaff = scaffolder or ProjectScaffolder()
    try:
        report = scaff.scaffold(
            project_dir=resolved_dir,
            interactive=not non_interactive,
            sync_skills=not no_skills,
        )
        print(f"\n[Runner] Project initialized successfully at '{resolved_dir}'.")
        print(f"  Created configuration: {report.config_path}")
        return 0
    except ValueError as exc:
        print(f"\n[Runner] Error: {exc}")
        return 1
    except Exception as exc:
        print(f"\n[Runner] Error during initialization: {exc}")
        return 1


def run_skills_sync(
    project_dir: Path,
    force: bool = False,
    skills_client: SkillsClient | None = None,
) -> int:
    """Synchronize remote skills catalog into <project_dir>/.agents/skills/."""
    resolved_dir = Path(project_dir).resolve()
    if not resolved_dir.exists():
        print(f"\n[Runner] Error: Project directory '{resolved_dir}' does not exist.")
        return 1
    if not resolved_dir.is_dir():
        print(f"\n[Runner] Error: Project path '{resolved_dir}' is not a directory.")
        return 1

    client = skills_client
    if client is None:
        from runner.adapters.skills.skills_client import GitHubSkillsClient

        client = GitHubSkillsClient()

    try:
        result = client.sync_skills(project_dir=resolved_dir, force=force)
        print(f"\n[Runner] Skills synchronized successfully for '{resolved_dir}'.")
        print(f"  Installed: {len(result.installed_skills)}")
        print(f"  Updated:   {len(result.updated_skills)}")
        print(f"  Preserved: {len(result.preserved_skills)}")
        if result.errors:
            print(f"  Errors:    {len(result.errors)}")
            for err in result.errors:
                print(f"    - {err}")
            return 1
        return 0
    except Exception as exc:
        print(f"\n[Runner] Error: Skills synchronization failed: {exc}")
        return 1


def main(
    argv: Sequence[str] | None = None,
    *,
    gateway: DiscordGateway | None = None,
    container_instance: BotContainer | None = None,
) -> int:
    """Main CLI entry point returning status exit code."""
    parser = create_parser()
    args = parser.parse_args(argv)

    raw_project_dir = getattr(args, "project_dir", None)
    if raw_project_dir is not None:
        if "\0" in str(raw_project_dir):
            print("\n[Runner] Error: Invalid project_dir: contains null byte")
            return 1
        try:
            project_dir = Path(raw_project_dir).resolve()
        except (ValueError, RuntimeError) as exc:
            print(f"\n[Runner] Error: Invalid project directory '{raw_project_dir}': {exc}")
            return 1

        if args.command != "init":
            if not project_dir.exists():
                print(f"\n[Runner] Error: Project directory '{project_dir}' does not exist.")
                return 1
            if not project_dir.is_dir():
                print(f"\n[Runner] Error: Project path '{project_dir}' is not a directory.")
                return 1
        else:
            if project_dir.exists() and not project_dir.is_dir():
                print(f"\n[Runner] Error: Project path '{project_dir}' is not a directory.")
                return 1
    else:
        project_dir = Path.cwd().resolve()

    if not args.command:
        parser.print_help()
        return 0

    local_only = getattr(args, "local_only", False)
    config_path = getattr(args, "config", None)

    try:
        if args.command == "init":
            return run_init(
                project_dir=project_dir,
                ai_prompt=getattr(args, "ai_prompt", False),
                non_interactive=getattr(args, "non_interactive", False),
                no_skills=getattr(args, "no_skills", False),
            )
        elif args.command == "skills":
            action = getattr(args, "skills_action", None)
            if action == "sync":
                return run_skills_sync(
                    project_dir=project_dir,
                    force=getattr(args, "force", False),
                )
            parser.print_help()
            return 0
        elif args.command == "doctor":
            return asyncio.run(
                run_doctor(
                    config_path=config_path,
                    local_only=local_only,
                    live=getattr(args, "live", False),
                    project_dir=project_dir,
                )
            )
        elif args.command == "start":
            return asyncio.run(
                run_start(
                    config_path=config_path,
                    local_only=local_only,
                    model_id=getattr(args, "model", None),
                    project_dir=project_dir,
                )
            )
        elif args.command == "bot":
            return asyncio.run(
                run_bot(
                    config_path=config_path,
                    smoke=getattr(args, "smoke", False),
                    run=getattr(args, "run", False),
                    container_instance=container_instance,
                    gateway=gateway,
                    project_dir=project_dir,
                )
            )
        elif args.command == "notify":
            return asyncio.run(
                run_notify(
                    message=args.message,
                    config_path=config_path,
                    container_instance=container_instance,
                    gateway=gateway,
                    project_dir=project_dir,
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
