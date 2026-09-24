"""Application use cases and interactors for Ticket Runner."""

from runner.application.crash_recovery import (
    CrashRecoveryCoordinator,
    RecoveryResult,
)
from runner.application.discord_thread_manager import DiscordThreadManager
from runner.application.doctor import CheckResult, Doctor, DoctorReport
from runner.application.evidence_triage import EvidenceTriage, TriageResult
from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    GatekeeperVerificationLoop,
    VerificationLoop,
    VerificationLoopResult,
    VerificationLoopStatus,
    VerificationReport,
    WorkerCycleRunner,
    build_verification_failure_prompt,
    inject_test_timeout,
)
from runner.application.git_operations import GitOperations
from runner.application.handoff_coordinator import (
    CEILING,
    CHECKPOINT_MISSING,
    CHECKPOINT_STALE,
    ESCALATED,
    EscalationNotice,
    HandoffCoordinator,
    READY,
    SingleCycleResult,
    SingleCycleStatus,
    WorkerRunResult,
    default_recovery_confirmation,
)
from runner.application.prompt_builder import (
    DEFAULT_INVARIANTS,
    PromptBuilder,
    build_prompt,
    extract_invariants,
)
from runner.application.queue_orchestrator import (
    QueueOrchestrator,
    TicketOutcome,
    TicketOutcomeStatus,
    TicketProcessor,
)
from runner.application.state_coordinator import StateCoordinator
from runner.application.ticket_processor import GatekeeperTicketProcessor


__all__ = [
    "CEILING",
    "CHECKPOINT_MISSING",
    "CHECKPOINT_STALE",
    "CheckResult",
    "CommandOutcome",
    "CrashRecoveryCoordinator",
    "DEFAULT_INVARIANTS",
    "DiscordThreadManager",
    "Doctor",
    "DoctorReport",
    "ESCALATED",
    "EscalationNotice",
    "EvidenceTriage",
    "GatekeeperCommandExecutor",
    "GatekeeperTicketProcessor",
    "GatekeeperVerificationLoop",
    "GitOperations",
    "HandoffCoordinator",
    "PromptBuilder",
    "QueueOrchestrator",
    "READY",
    "RecoveryResult",
    "SingleCycleResult",
    "SingleCycleStatus",
    "StateCoordinator",
    "TicketOutcome",
    "TicketOutcomeStatus",
    "TicketProcessor",
    "TriageResult",
    "VerificationLoop",
    "VerificationLoopResult",
    "VerificationLoopStatus",
    "VerificationReport",
    "WorkerCycleRunner",
    "WorkerRunResult",
    "build_prompt",
    "build_verification_failure_prompt",
    "default_recovery_confirmation",
    "extract_invariants",
    "inject_test_timeout",
]

