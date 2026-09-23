"""Root pytest configuration and shared fixtures."""

from pathlib import Path
import pytest

from runner.adapters.opencode.opencode_worker import OpenCodeWorker
from runner.application.worker_supervisor import WorkerSupervisor

WorkerSupervisor.set_default_agent_worker_factory(OpenCodeWorker)


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary directory Path."""
    return tmp_path
