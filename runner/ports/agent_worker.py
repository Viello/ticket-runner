"""AgentWorker port protocol defining the interface for agent CLI adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runner.domain.telemetry import WorkerEvent


@runtime_checkable
class AgentWorker(Protocol):
    """Protocol for driving coding agent processes, decoding events, and detecting resources."""

    def build_run_command(
        self,
        prompt: str,
        session_id: str | None = None,
        variant: str | None = None,
        model_id: str | None = None,
    ) -> list[str]:
        """Construct the argv command list for launching or resuming the agent process."""
        ...

    def decode_event(self, line: str) -> WorkerEvent | None:
        """Decode a single raw stdout line into a normalized WorkerEvent domain model."""
        ...

    def extract_resource_access(
        self,
        event: WorkerEvent | None = None,
        raw_line: str | None = None,
    ) -> frozenset[str]:
        """Detect project-local skill and AGENTS.md resource accesses from event stream."""
        ...
