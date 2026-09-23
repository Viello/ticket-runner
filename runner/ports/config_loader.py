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

    def load_two_tier(
        self,
        project_dir: Path | str,
        global_path: Path | str | None = None,
        project_config_path: Path | str | None = None,
    ) -> RunnerConfig:
        """Load and merge two-tier configuration (global user defaults + project overlay).

        Args:
            project_dir: Root directory of the project.
            global_path: Optional path to global user configuration file.
            project_config_path: Optional path to project overlay configuration file.

        Returns:
            RunnerConfig domain object.

        Raises:
            ConfigError: If configuration files cannot be read or validation fails.
        """
        ...

    def persist_session_terminal(self, path: Path | str, session_terminal: str) -> None:
        """Persist the selected session terminal to configuration storage.

        Args:
            path: Path to the configuration file.
            session_terminal: The terminal executable name (e.g. 'wt.exe').

        Raises:
            ConfigError: If writing to the configuration file fails.
        """
        ...
