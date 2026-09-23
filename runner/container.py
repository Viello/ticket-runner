"""Composition Root for Ticket Runner wiring adapters to interactors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import shutil
import time
from typing import Any

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.adapters.discord.client import DiscordClient
from runner.adapters.filesystem.json_state_store import JsonStateStore
from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.adapters.json_status_publisher import JsonFileStatusPublisher
from runner.adapters.markdown.file_lock import DEFAULT_LOCK_PATH, QueueFileLock
from runner.adapters.markdown.gotchas_store import DEFAULT_GOTCHAS_PATH, GotchasStore
from runner.adapters.markdown.spec_parser import SpecMarkdownParser
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.adapters.opencode.opencode_worker import OpenCodeWorker
from runner.adapters.ui.terminal import RichTerminalDisplay
from runner.adapters.ui.terminal_detector import TerminalHostDetector
from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway
from runner.adapters.ui.tui_launcher import TuiLauncher
from runner.application.clean_slate import CleanSlateArchiver
from runner.application.crash_recovery import CrashRecoveryCoordinator
from runner.application.gatekeeper import GatekeeperCommandExecutor
from runner.application.git_operations import GitOperations
from runner.application.handoff_coordinator import EscalationNotice, HandoffCoordinator
from runner.application.presence_coordinator import PresenceCoordinator
from runner.application.prompt_builder import PromptBuilder
from runner.application.queue_orchestrator import DEFAULT_TICKETS_DIR, QueueOrchestrator
from runner.application.state_coordinator import StateCoordinator
from runner.application.ticket_processor import TicketProcessor
from runner.application.tui_coordinator import TuiCoordinator
from runner.application.worker_supervisor import WorkerSupervisor
from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    VerificationConfig,
    WorkerConfig,
)
from runner.domain.runtime_paths import RuntimePaths
from runner.ports.agent_worker import AgentWorker
from runner.ports.command_runner import CommandRunner
from runner.ports.intervention import InterventionGateway
from runner.ports.signal_repository import SignalRepository
from runner.ports.state_store import StateStore
from runner.ports.status_publisher import StatusPublisher
from runner.ports.terminal_display import TerminalDisplay, UiEventSink
from runner.ports.ticket_repository import TicketRepository


def _default_config() -> RunnerConfig:
    """Construct safe fallback configuration when no config file is provided."""
    return RunnerConfig(
        project=ProjectConfig(name="ticket-runner", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
    )


@dataclass(frozen=True)
class RunnerContainer:
    """Wired composition root container for Ticket Runner."""

    config: RunnerConfig
    orchestrator: QueueOrchestrator
    processor: TicketProcessor
    coordinator: HandoffCoordinator
    supervisor: WorkerSupervisor
    signal_repository: SignalRepository
    intervention_gateway: InterventionGateway
    executor: GatekeeperCommandExecutor
    git_operations: GitOperations
    ticket_store: TicketRepository
    gotchas_store: GotchasStore
    lock: QueueFileLock
    runtime_paths: RuntimePaths
    command_runner: CommandRunner
    state_coordinator: StateCoordinator
    state_store: StateStore
    crash_recovery: CrashRecoveryCoordinator
    status_publisher: StatusPublisher | None = None
    terminal_display: TerminalDisplay | None = None
    ui_event_sink: UiEventSink | None = None
    presence_coordinator: PresenceCoordinator | None = None
    tui_launcher: TuiLauncher | None = None
    tui_coordinator: TuiCoordinator | None = None
    discord_thread_manager: Any | None = None
    discord_logger: Any | None = None
    agent_worker: AgentWorker | None = None


def build_container(
    config: RunnerConfig | None = None,
    *,
    model_id: str | None = None,
    command_runner: CommandRunner | None = None,
    intervention_gateway: InterventionGateway | None = None,
    ticket_store: TicketRepository | None = None,
    gotchas_store: GotchasStore | None = None,
    signal_repository: SignalRepository | None = None,
    lock: QueueFileLock | None = None,
    git_operations: GitOperations | None = None,
    runtime_paths: RuntimePaths | None = None,
    executor: GatekeeperCommandExecutor | None = None,
    prompt_builder: PromptBuilder | None = None,
    spec_parser: SpecMarkdownParser | None = None,
    supervisor: WorkerSupervisor | None = None,
    coordinator: HandoffCoordinator | None = None,
    processor: TicketProcessor | None = None,
    orchestrator: QueueOrchestrator | None = None,
    clean_slate_archiver: CleanSlateArchiver | None = None,
    state_store: StateStore | None = None,
    state_coordinator: StateCoordinator | None = None,
    cwd: Path | None = None,
    clock: Callable[[], float] | None = None,
    printer: Callable[[str], None] | None = print,
    notify: Callable[[str | EscalationNotice], None] | None = None,
    tickets_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    gotchas_path: Path | str | None = None,
    commit_scope: str = "queue",
    spec_slug: str | None = None,
    crash_recovery: CrashRecoveryCoordinator | None = None,
    terminal_display: TerminalDisplay | None = None,
    ui_event_sink: UiEventSink | None = None,
    presence_coordinator: PresenceCoordinator | None = None,
    tui_launcher: TuiLauncher | None = None,
    tui_coordinator: TuiCoordinator | None = None,
    status_publisher: StatusPublisher | None = None,
    console: Any | None = None,
    terminal_detector: Any | None = None,
    discord_thread_manager: Any | None = None,
    discord_logger: Any | None = None,
    agent_worker: AgentWorker | None = None,
) -> RunnerContainer:
    """Build and wire the complete runner pipeline with optional keyword-only overrides."""
    resolved_config: RunnerConfig
    if config is not None:
        resolved_config = config
    else:
        config_file = (cwd / "config.yaml") if cwd else Path("config.yaml")
        if config_file.is_file():
            resolved_config = YamlConfigLoader().load(config_file)
        else:
            resolved_config = _default_config()

    resolved_command_runner = command_runner or SubprocessRunner()

    resolved_runtime_paths = runtime_paths or (
        RuntimePaths(root_dir=cwd / ".agent") if cwd else RuntimePaths()
    )

    resolved_signal_repo = signal_repository or FilesystemSignalRepository(
        runtime_paths=resolved_runtime_paths
    )

    resolved_intervention_gateway = intervention_gateway or TerminalInterventionGateway()

    resolved_ticket_store = ticket_store or DirectoryTicketStore(
        root_dir=tickets_dir or (cwd / DEFAULT_TICKETS_DIR if cwd else DEFAULT_TICKETS_DIR)
    )

    resolved_gotchas_store = gotchas_store or GotchasStore(
        path=gotchas_path or (cwd / DEFAULT_GOTCHAS_PATH if cwd else DEFAULT_GOTCHAS_PATH)
    )

    resolved_lock = lock or QueueFileLock(
        lock_path=lock_path or (cwd / DEFAULT_LOCK_PATH if cwd else DEFAULT_LOCK_PATH)
    )

    resolved_git_ops = git_operations or GitOperations(
        runner=resolved_command_runner,
        commit_prefix=resolved_config.git.commit_prefix,
        cwd=cwd,
    )

    resolved_terminal_display = terminal_display or RichTerminalDisplay(console=console)
    resolved_event_sink = ui_event_sink or resolved_terminal_display

    resolved_executor = executor or GatekeeperCommandExecutor(
        command_runner=resolved_command_runner,
        cwd=cwd,
        ui_event_sink=resolved_event_sink,
    )
    if hasattr(resolved_executor, "ui_event_sink") and resolved_executor.ui_event_sink is None and resolved_event_sink is not None:
        resolved_executor.ui_event_sink = resolved_event_sink

    resolved_state_store = state_store or JsonStateStore(
        path=resolved_runtime_paths.state_path
    )

    resolved_state_coordinator = state_coordinator or StateCoordinator(
        state_store=resolved_state_store,
        branch=resolved_config.project.branch,
        selected_model=model_id,
        clock=clock,
        terminal_display=resolved_terminal_display,
    )

    resolved_prompt_builder = prompt_builder or PromptBuilder()
    resolved_spec_parser = spec_parser or SpecMarkdownParser()

    resolved_status_publisher = status_publisher or JsonFileStatusPublisher(
        target=resolved_runtime_paths.status_file
    )

    WorkerSupervisor.set_default_agent_worker_factory(OpenCodeWorker)
    resolved_agent_worker = agent_worker or OpenCodeWorker()

    resolved_supervisor = supervisor or WorkerSupervisor(
        command_runner=resolved_command_runner,
        runtime_paths=resolved_runtime_paths,
        budget_config=resolved_config.tokens,
        notify=notify,
        cwd=cwd,
        clock=clock or time.monotonic,
        signal_repository=resolved_signal_repo,
        default_reasoning=resolved_config.model.default_reasoning,
        model_id=model_id,
        state_coordinator=resolved_state_coordinator,
        ui_event_sink=resolved_event_sink,
        status_publisher=resolved_status_publisher,
        presence_mode=resolved_config.presence.default_mode,
        printer=printer,
        max_attempts=resolved_config.verification.max_attempts,
        agent_worker=resolved_agent_worker,
    )
    if resolved_supervisor.state_coordinator is None:
        resolved_supervisor.state_coordinator = resolved_state_coordinator
    if hasattr(resolved_supervisor, "ui_event_sink") and resolved_supervisor.ui_event_sink is None and resolved_event_sink is not None:
        resolved_supervisor.ui_event_sink = resolved_event_sink
    if hasattr(resolved_supervisor, "status_publisher") and resolved_supervisor.status_publisher is None:
        resolved_supervisor.status_publisher = resolved_status_publisher

    resolved_coordinator = coordinator or HandoffCoordinator(
        supervisor=resolved_supervisor,
        prompt_builder=resolved_prompt_builder,
        runtime_paths=resolved_runtime_paths,
        gotchas_store=resolved_gotchas_store,
        spec_parser=resolved_spec_parser,
        worker_config=resolved_config.worker,
        budget_config=resolved_config.tokens,
        clock=clock or time.time,
        notify=notify,
        git_operations=resolved_git_ops,
        signal_repository=resolved_signal_repo,
    )

    resolved_processor = processor or TicketProcessor(
        coordinator=resolved_coordinator,
        signal_repository=resolved_signal_repo,
        executor=resolved_executor,
        intervention_gateway=resolved_intervention_gateway,
        verification_config=resolved_config.verification,
        max_attempts=resolved_config.verification.max_attempts,
        prompt_builder=resolved_prompt_builder,
        spec_parser=resolved_spec_parser,
        gotchas_store=resolved_gotchas_store,
        worker_config=resolved_config.worker,
        printer=printer,
        state_coordinator=resolved_state_coordinator,
        runtime_paths=resolved_runtime_paths,
        token_budget=resolved_config.tokens,
        status_publisher=resolved_status_publisher,
        git_operations=resolved_git_ops,
    )
    if hasattr(resolved_processor, "state_coordinator") and resolved_processor.state_coordinator is None:
        resolved_processor.state_coordinator = resolved_state_coordinator

    resolved_orchestrator = orchestrator or QueueOrchestrator(
        ticket_store=resolved_ticket_store,
        lock=resolved_lock,
        gotchas_store=resolved_gotchas_store,
        git_operations=resolved_git_ops,
        processor=resolved_processor,
        tickets_dir=tickets_dir,
        lock_path=lock_path,
        gotchas_path=gotchas_path,
        commit_scope=commit_scope,
        spec_slug=spec_slug,
        cwd=cwd,
        clean_slate_archiver=clean_slate_archiver,
        clock=clock,
        state_coordinator=resolved_state_coordinator,
        ui_event_sink=resolved_event_sink,
    )
    if hasattr(resolved_orchestrator, "_state_coordinator") and resolved_orchestrator.state_coordinator is None:
        resolved_orchestrator._state_coordinator = resolved_state_coordinator
    if hasattr(resolved_orchestrator, "ui_event_sink") and resolved_orchestrator.ui_event_sink is None and resolved_event_sink is not None:
        resolved_orchestrator.ui_event_sink = resolved_event_sink

    resolved_crash_recovery = crash_recovery or CrashRecoveryCoordinator(
        state_store=resolved_state_store,
        git_operations=resolved_git_ops,
        worker_supervisor=resolved_supervisor,
        state_coordinator=resolved_state_coordinator,
        runtime_paths=resolved_runtime_paths,
        ticket_store=resolved_ticket_store,
        printer=printer,
        clock=clock,
    )

    idle_esc_min = getattr(getattr(resolved_config, "presence", None), "idle_escalation_minutes", 3)
    resolved_presence_coordinator = presence_coordinator or PresenceCoordinator(
        state_coordinator=resolved_state_coordinator,
        terminal_display=resolved_terminal_display,
        ui_event_sink=resolved_event_sink,
        idle_escalation_minutes=idle_esc_min,
    )

    if hasattr(resolved_processor, "discord_thread_manager") and resolved_processor.discord_thread_manager is None:
        resolved_processor.discord_thread_manager = discord_thread_manager
    if hasattr(resolved_processor, "discord_logger") and resolved_processor.discord_logger is None:
        resolved_processor.discord_logger = discord_logger
    if hasattr(resolved_processor, "presence_coordinator") and resolved_processor.presence_coordinator is None:
        resolved_processor.presence_coordinator = resolved_presence_coordinator
    if hasattr(resolved_processor, "runner_config") and resolved_processor.runner_config is None:
        resolved_processor.runner_config = resolved_config

    if hasattr(resolved_orchestrator, "discord_thread_manager") and resolved_orchestrator.discord_thread_manager is None:
        resolved_orchestrator._discord_thread_manager = discord_thread_manager
    if hasattr(resolved_orchestrator, "discord_logger") and resolved_orchestrator.discord_logger is None:
        resolved_orchestrator._discord_logger = discord_logger
    if hasattr(resolved_orchestrator, "presence_coordinator") and resolved_orchestrator.presence_coordinator is None:
        resolved_orchestrator._presence_coordinator = resolved_presence_coordinator
    if hasattr(resolved_orchestrator, "runner_config") and resolved_orchestrator.runner_config is None:
        resolved_orchestrator._runner_config = resolved_config

    resolved_tui_launcher = tui_launcher or TuiLauncher(
        command_runner=resolved_command_runner,
    )

    raw_terminal_host = getattr(getattr(resolved_config, "ui", None), "session_terminal", "")
    if not raw_terminal_host or raw_terminal_host.lower() == "auto":
        detector_fn = terminal_detector or TerminalHostDetector
        if hasattr(detector_fn, "detect"):
            detected_host = detector_fn.detect()
        elif callable(detector_fn):
            try:
                detected_host = detector_fn(path_resolver=shutil.which)
            except TypeError:
                detected_host = detector_fn()
        else:
            detected_host = None
        resolved_terminal_host = detected_host or "wt.exe"
    else:
        resolved_terminal_host = raw_terminal_host

    resolved_tui_coordinator = tui_coordinator or TuiCoordinator(
        terminal_display=resolved_terminal_display,
        launcher=resolved_tui_launcher,
        state_coordinator=resolved_state_coordinator,
        terminal_host=resolved_terminal_host,
        supervisor=resolved_supervisor,
        ui_event_sink=resolved_event_sink,
        cwd=cwd,
    )

    if resolved_supervisor.tui_coordinator is None:
        resolved_supervisor.tui_coordinator = resolved_tui_coordinator

    return RunnerContainer(
        config=resolved_config,
        orchestrator=resolved_orchestrator,
        processor=resolved_processor,
        coordinator=resolved_coordinator,
        supervisor=resolved_supervisor,
        signal_repository=resolved_signal_repo,
        intervention_gateway=resolved_intervention_gateway,
        executor=resolved_executor,
        git_operations=resolved_git_ops,
        ticket_store=resolved_ticket_store,
        gotchas_store=resolved_gotchas_store,
        lock=resolved_lock,
        runtime_paths=resolved_runtime_paths,
        command_runner=resolved_command_runner,
        state_coordinator=resolved_state_coordinator,
        state_store=resolved_state_store,
        crash_recovery=resolved_crash_recovery,
        status_publisher=resolved_status_publisher,
        terminal_display=resolved_terminal_display,
        ui_event_sink=resolved_event_sink,
        presence_coordinator=resolved_presence_coordinator,
        tui_launcher=resolved_tui_launcher,
        tui_coordinator=resolved_tui_coordinator,
        discord_thread_manager=discord_thread_manager,
        discord_logger=discord_logger,
        agent_worker=resolved_agent_worker,
    )


@dataclass(frozen=True)
class BotContainer:
    """Minimal container for Discord bot standalone execution (T075)."""

    config: RunnerConfig
    runtime_paths: RuntimePaths
    signal_repository: SignalRepository
    discord_client: DiscordClient
    state_store: StateStore | None = None


def build_bot_container(
    config: RunnerConfig | None = None,
    *,
    config_path: Path | str | None = None,
    runtime_paths: RuntimePaths | None = None,
    signal_repository: SignalRepository | None = None,
    state_store: StateStore | None = None,
    discord_client: DiscordClient | None = None,
    cwd: Path | None = None,
) -> BotContainer:
    """Build and wire a minimal container for standalone bot operations (T075)."""
    resolved_config: RunnerConfig
    if config is not None:
        resolved_config = config
    else:
        path = Path(config_path) if config_path else ((cwd / "config.yaml") if cwd else Path("config.yaml"))
        if path.is_file():
            resolved_config = YamlConfigLoader().load(path)
        else:
            resolved_config = _default_config()

    resolved_runtime_paths = runtime_paths or (
        RuntimePaths(root_dir=cwd / ".agent") if cwd else RuntimePaths()
    )

    resolved_signal_repo = signal_repository or FilesystemSignalRepository(
        runtime_paths=resolved_runtime_paths
    )

    resolved_state_store = state_store or JsonStateStore(
        path=resolved_runtime_paths.state_path
    )

    resolved_discord_client = discord_client or DiscordClient(
        config=resolved_config,
        state_store=resolved_state_store,
        signal_repository=resolved_signal_repo,
    )

    return BotContainer(
        config=resolved_config,
        runtime_paths=resolved_runtime_paths,
        signal_repository=resolved_signal_repo,
        discord_client=resolved_discord_client,
        state_store=resolved_state_store,
    )


