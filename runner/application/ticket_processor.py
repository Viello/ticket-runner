"""Ticket processor application interactor driving the ready-path verification loop (T032)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecExcerpt, SpecMarkdownParser
from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway
from runner.application.gatekeeper import (
    GatekeeperCommandExecutor,
    VerificationLoop,
    WorkerCycleRunner,
)
from runner.application.handoff_coordinator import (
    HandoffCoordinator,
    WorkerRunResult,
)
from runner.application.prompt_builder import PromptBuilder
from runner.application.queue_orchestrator import (
    TicketOutcome,
    TicketOutcomeStatus,
    TicketProcessor as TicketProcessorProtocol,
)
from runner.domain.config import VerificationConfig, WorkerConfig
from runner.domain.exceptions import UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal
from runner.domain.ticket import Ticket
from runner.ports.intervention import InterventionGateway
from runner.ports.signal_repository import SignalRepository

_DEFAULT_PRINTER: Callable[[str], None] = print


class GatekeeperTicketProcessor:
    """Processes a single Ticket through signal isolation, prompt building, and Gatekeeper verification."""

    def __init__(
        self,
        coordinator: HandoffCoordinator | None = None,
        cycle_runner: WorkerCycleRunner | Callable[..., Awaitable[WorkerRunResult]] | None = None,
        signal_repository: SignalRepository | None = None,
        executor: GatekeeperCommandExecutor | None = None,
        intervention_gateway: InterventionGateway | None = None,
        verification_config: VerificationConfig | None = None,
        max_attempts: int | None = None,
        prompt_builder: PromptBuilder | None = None,
        spec_parser: SpecMarkdownParser | None = None,
        gotchas_store: GotchasStore | None = None,
        worker_config: WorkerConfig | None = None,
        loop_factory: Callable[..., VerificationLoop] | None = None,
        printer: Callable[[str], None] | None = _DEFAULT_PRINTER,
    ) -> None:
        self._coordinator = coordinator

        if signal_repository is not None:
            self._signal_repository = signal_repository
        elif coordinator is not None and getattr(coordinator, "signal_repository", None) is not None:
            self._signal_repository = coordinator.signal_repository
        else:
            self._signal_repository = FilesystemSignalRepository(RuntimePaths())

        if cycle_runner is not None:
            self._cycle_runner = cycle_runner
        elif coordinator is not None:
            self._cycle_runner = coordinator.run_cycle
        else:
            self._cycle_runner = None

        self._executor = executor or GatekeeperCommandExecutor()
        self._intervention_gateway = intervention_gateway or TerminalInterventionGateway()
        self._verification_config = verification_config
        self._max_attempts = max_attempts
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._spec_parser = spec_parser or SpecMarkdownParser()
        self._gotchas_store = gotchas_store
        self._worker_config = worker_config
        self._loop_factory = loop_factory
        self._printer = printer

    @property
    def signal_repository(self) -> SignalRepository:
        """Signal repository port used for isolation and ready consumption."""
        return self._signal_repository

    @property
    def cycle_runner(self) -> WorkerCycleRunner | Callable[..., Awaitable[WorkerRunResult]] | None:
        """Configured worker cycle runner."""
        return self._cycle_runner

    @property
    def executor(self) -> GatekeeperCommandExecutor:
        """Gatekeeper command verification executor."""
        return self._executor

    @property
    def intervention_gateway(self) -> InterventionGateway:
        """Human intervention gateway."""
        return self._intervention_gateway

    def build_initial_prompt(
        self,
        ticket: Ticket,
        spec_excerpt: SpecExcerpt | str | None = None,
    ) -> str:
        """Build initial worker prompt with documented ready signal schema and question protocol."""
        if self._coordinator is not None and hasattr(self._coordinator, "build_initial_prompt"):
            return self._coordinator.build_initial_prompt(ticket, spec_excerpt=spec_excerpt)

        resolved_excerpt: SpecExcerpt | str
        if spec_excerpt is not None:
            resolved_excerpt = spec_excerpt
        elif ticket.spec_path and Path(ticket.spec_path).is_file():
            try:
                resolved_excerpt = self._spec_parser.extract_excerpt(ticket.spec_path)
            except Exception:
                resolved_excerpt = f"Full specification reference: `{ticket.spec_path}`"
        else:
            resolved_excerpt = f"Full specification reference: `{ticket.spec_path}`"

        global_gotchas = (
            self._gotchas_store.load()
            if self._gotchas_store is not None
            else ""
        )
        execution_skill = (
            self._worker_config.execution_skill
            if self._worker_config is not None
            else ".agents/skills/implement/SKILL.md"
        )

        return self._prompt_builder.build(
            ticket=ticket,
            spec_excerpt=resolved_excerpt,
            global_gotchas=global_gotchas,
            execution_skill=execution_skill,
        )

    async def __call__(self, ticket: Ticket) -> TicketOutcome:
        """Execute and verify a single ticket, returning its outcome."""
        return await self.process(ticket)

    async def process(self, ticket: Ticket) -> TicketOutcome:
        """Drive the ready-path verification loop for a ticket."""
        if self._cycle_runner is None:
            raise RuntimeError(
                "No worker cycle runner configured for TicketProcessor."
            )

        # 1. Purge stale Signals for the Ticket at start (Isolation Layer)
        self._signal_repository.purge(ticket.id)

        # 2. Build initial Worker prompt
        initial_prompt = self.build_initial_prompt(ticket)

        # 3. Create and drive VerificationLoop
        if self._loop_factory is not None:
            loop = self._loop_factory(
                ticket=ticket,
                cycle_runner=self._cycle_runner,
                signal_repository=self._signal_repository,
                executor=self._executor,
                intervention_gateway=self._intervention_gateway,
                verification_config=self._verification_config,
                max_attempts=self._max_attempts,
                initial_prompt=initial_prompt,
            )
        else:
            loop = VerificationLoop(
                ticket=ticket,
                cycle_runner=self._cycle_runner,
                signal_repository=self._signal_repository,
                executor=self._executor,
                intervention_gateway=self._intervention_gateway,
                verification_config=self._verification_config,
                max_attempts=self._max_attempts,
                initial_prompt=initial_prompt,
            )

        try:
            result = await loop.run()
        except UserAbortError as exc:
            return TicketOutcome.aborted(details=str(exc))

        # 4. Map verification loop result to TicketOutcome
        if result.is_passed:
            ready_signal = result.ready_signal
            if ready_signal is not None:
                changes = tuple(f"Update {p}" for p in ready_signal.modified_files)
                new_gotchas = ready_signal.new_gotchas
                scope = ready_signal.scope
                if ready_signal.self_review_notes and self._printer is not None:
                    self._printer(f"[{ticket.id}] Self-review notes: {ready_signal.self_review_notes}")
            else:
                changes = ()
                new_gotchas = ()
                scope = None

            return TicketOutcome.approved(
                new_gotchas=new_gotchas,
                changes=changes,
                scope=scope,
            )

        if result.is_skipped:
            diagnostics = result.diagnostics or loop.last_diagnostics or ""
            return TicketOutcome.skipped(details=diagnostics)

        if result.is_question_pending:
            raise NotImplementedError(
                f"Question handling for ticket '{ticket.id}' will be implemented in T033."
            )

        raise ValueError(f"Unsupported verification loop status: {result.status}")


TicketProcessor = GatekeeperTicketProcessor
