"""Composition Root for Ticket Runner wiring adapters to interactors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.adapters.markdown.file_lock import DEFAULT_LOCK_PATH, QueueFileLock
from runner.adapters.markdown.gotchas_store import DEFAULT_GOTCHAS_PATH, GotchasStore
from runner.adapters.markdown.spec_parser import SpecMarkdownParser
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway
from runner.application.clean_slate import CleanSlateArchiver
from runner.application.gatekeeper import GatekeeperCommandExecutor
from runner.application.git_operations import GitOperations
from runner.application.handoff_coordinator import EscalationNotice, HandoffCoordinator
from runner.application.prompt_builder import PromptBuilder
from runner.application.queue_orchestrator import DEFAULT_TICKETS_DIR, QueueOrchestrator
from runner.application.ticket_processor import TicketProcessor
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
from runner.ports.command_runner import CommandRunner
from runner.ports.intervention import InterventionGateway
from runner.ports.signal_repository import SignalRepository
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


def build_container(
    config: RunnerConfig | None = None,
    *,
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
    cwd: Path | None = None,
    clock: Callable[[], float] | None = None,
    printer: Callable[[str], None] | None = print,
    notify: Callable[[str | EscalationNotice], None] | None = None,
    tickets_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    gotchas_path: Path | str | None = None,
    commit_scope: str = "queue",
    spec_slug: str | None = None,
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

    resolved_executor = executor or GatekeeperCommandExecutor(
        command_runner=resolved_command_runner,
        cwd=cwd,
    )

    resolved_prompt_builder = prompt_builder or PromptBuilder()
    resolved_spec_parser = spec_parser or SpecMarkdownParser()

    resolved_supervisor = supervisor or WorkerSupervisor(
        command_runner=resolved_command_runner,
        runtime_paths=resolved_runtime_paths,
        budget_config=resolved_config.tokens,
        notify=notify,
        cwd=cwd,
        clock=clock or time.monotonic,
        signal_repository=resolved_signal_repo,
    )

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
    )

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
    )

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
    )
