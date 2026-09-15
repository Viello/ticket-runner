"""ConfigLoader protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from runner.domain.config import RunnerConfig


@runtime_checkable
class ConfigLoader(Protocol):
    """Abstract protocol for loading and validating runner configuration."""

    def load(self, path: Path | str) -> RunnerConfig:
        """Load and validate configuration from a file path.

        Args:
            path: Path to the configuration file.

        Returns:
            RunnerConfig domain object.

        Raises:
            ConfigError: If the file does not exist, syntax is invalid, or schema validation fails.
        """
        ...
