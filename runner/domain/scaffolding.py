"""Domain entities and value objects for project scaffolding and heuristics."""

from __future__ import annotations

from dataclasses import dataclass

from runner.domain.config import VALID_WORKER_PROVIDERS
from runner.domain.exceptions import ConfigError


@dataclass(frozen=True)
class ProjectHeuristics:
    """Detected project heuristics and recommended scaffolding configuration."""

    name: str
    detected_stack: str
    test_cmd: str
    build_cmd: str = ""
    base_branch: str = "main"
    branch: str = "agent/ticket-runner"
    provider: str = "opencode"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigError("Project name must be a non-empty string")
        if not isinstance(self.detected_stack, str) or not self.detected_stack.strip():
            raise ConfigError("Detected stack must be a non-empty string")
        if not isinstance(self.test_cmd, str):
            raise ConfigError("Test command must be a string")
        if not isinstance(self.build_cmd, str):
            raise ConfigError("Build command must be a string")
        if not isinstance(self.base_branch, str) or not self.base_branch.strip():
            raise ConfigError("Base branch must be a non-empty string")
        if not isinstance(self.branch, str) or not self.branch.strip():
            raise ConfigError("Branch must be a non-empty string")
        if not isinstance(self.provider, str) or self.provider not in VALID_WORKER_PROVIDERS:
            raise ConfigError(
                f"Worker provider must be one of {sorted(VALID_WORKER_PROVIDERS)}, got: '{self.provider}'"
            )
